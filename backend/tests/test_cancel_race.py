"""取消竞态回归测试 — 后台上游推送必须感知「本地订阅已被取消」。

生产实证（2026-10-02 00:10，backend/logs/unisub.log）：
    00:10:17.665 订阅 盗梦空间 (tmdb 27205)
    00:10:17.772 取消（+107ms）
    00:10:32.740 MP 镜像 — 创建订阅: 盗梦空间 电影 (mp_sub_id=2263)（取消后 +15s）
本地 subscriptions / mp_subscription 均 0 行 → MP 侧留下「僵尸订阅」。

根因：schedule_upstream 派生的后台任务在请求返回后独立跑，每个上游调用前
不重查本地行；取消（删行）落在 NF 推送（~1s）与 MP 建订阅（实测 12~15s）之间时，
上游照旧建订阅。

契约（docs/SPEC-CANCEL-RACE.md §1/§2）：每个上游调用前重查本地行，
行不存在 → 放弃该步 + 落 action="system" 可见日志；判定只读库，不用内存标记。
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.models.activity_log import ActivityLog
from app.models.subscription import Subscription
from app.services.orchestrator import OrchestratorService

TITLE = "盗梦空间"
TMDB_MOVIE = 27205
SKIP_MARK = "订阅已取消，跳过上游推送"


class FakeNfCancel:
    """NextFind 桩 — 记录建订阅调用；可阻塞在 add 里，复现「取消落在 NF 推送途中」。"""

    def __init__(self, gate: asyncio.Event | None = None):
        self.gate = gate
        self.add_calls: list[int] = []
        self.remove_calls: list[int] = []
        self.entered = asyncio.Event()

    async def add_subscription(self, tmdb_id: int, media_type: str | None = None, title: str | None = None) -> dict:
        self.add_calls.append(tmdb_id)
        self.entered.set()
        if self.gate is not None:
            await self.gate.wait()  # 卡住：由测试在「取消」之后放行
        return {"id": "nf-cancel-1"}

    async def remove_subscription(self, tmdb_id: int, media_type: str | None = None) -> dict:
        self.remove_calls.append(tmdb_id)
        return {}


class FakeMpMirror:
    """MoviePilot 桩 — 记录建订阅调用（僵尸订阅就是在这里被建出来的）。"""

    def __init__(self):
        self.created: list[dict] = []

    async def find_subscription(self, tmdb_id: int, season: int | None = None):
        return None

    async def create_subscription(
        self, tmdb_id: int, media_type: str, title: str, year: int | None = None, season: int | None = None
    ) -> dict:
        self.created.append({"tmdb_id": tmdb_id, "season": season})
        return {"success": True, "data": {"id": 9999}}


async def _system_logs(session) -> list[str]:
    """取本测试库里 action="system" 的活动日志消息。"""
    rows = (await session.execute(select(ActivityLog).where(ActivityLog.action == "system"))).scalars().all()
    return [row.message for row in rows]


async def test_cancel_before_task_runs_skips_upstream_push(db_session, session_factory, monkeypatch) -> None:
    """订阅 → 立即取消 → 触发后台任务：NF/MP 建订阅桩调用次数 = 0，且落可见跳过日志。"""
    nf, mp = FakeNfCancel(), FakeMpMirror()
    orch = OrchestratorService(nf, mp, session_factory=session_factory)

    # 订阅请求返回时后台任务尚未跑到「重查本地行」这一步（生产：取消只比订阅晚 107ms）。
    # 摘掉自动调度，由测试在取消之后显式触发，消除事件循环里谁先跑的随机性。
    monkeypatch.setattr(orch, "schedule_upstream", lambda sub_id: None)
    resp = await orch.subscribe(db_session, tmdb_id=TMDB_MOVIE, title=TITLE, media_type="movie")

    # 立即取消（真实取消路径：NF 移除 + 删本地行）
    result = await orch.unsubscribe(db_session, resp.id)
    assert result["success"] is True
    assert await db_session.get(Subscription, resp.id) is None

    # 触发后台任务
    await orch.sync_upstream(resp.id)

    assert nf.add_calls == [], "订阅已取消，不得再向上游建订阅"
    assert mp.created == [], "订阅已取消，不得再建 MP 镜像订阅"
    logs = await _system_logs(db_session)
    assert any(SKIP_MARK in message for message in logs), f"缺少可见跳过日志: {logs}"


async def test_cancel_during_nf_push_skips_mp_mirror(db_session, session_factory) -> None:
    """取消落在 NF 推送途中：NF 已发出（无法回收），但 MP 镜像必须被跳过。

    这是本卡真正要堵的窗口 —— 生产日志里 MP 建订阅发生在取消后 +15s，
    恰好落在「NF 推送归来 → MP 建订阅」之间。
    """
    gate = asyncio.Event()
    nf, mp = FakeNfCancel(gate=gate), FakeMpMirror()
    orch = OrchestratorService(nf, mp, session_factory=session_factory)

    resp = await orch.subscribe(db_session, tmdb_id=TMDB_MOVIE, title=TITLE, media_type="movie")

    # 等后台任务真的进了 NF 调用（此后它阻塞在 gate 上）
    await asyncio.wait_for(nf.entered.wait(), timeout=5)

    # 取消（真实取消路径）
    result = await orch.unsubscribe(db_session, resp.id)
    assert result["success"] is True

    gate.set()  # 放行 NF 调用，让后台任务继续跑
    errors = await orch.drain_upstream()
    assert errors == []

    assert nf.add_calls == [TMDB_MOVIE], "NF 调用已在飞，本卡不回收（非目标）"
    assert mp.created == [], "取消发生在 NF 推送途中，MP 镜像必须被跳过"
    logs = await _system_logs(db_session)
    assert any(SKIP_MARK in message for message in logs), f"缺少可见跳过日志: {logs}"


async def test_normal_push_still_writes_upstream(db_session, session_factory) -> None:
    """对照：没取消时（gate 不阻塞）上游照旧推送 —— 防「为了堵竞态把正常路径也堵死」。"""
    nf, mp = FakeNfCancel(), FakeMpMirror()
    orch = OrchestratorService(nf, mp, session_factory=session_factory)

    resp = await orch.subscribe(db_session, tmdb_id=TMDB_MOVIE, title=TITLE, media_type="movie")
    errors = await orch.drain_upstream()
    assert errors == []

    assert nf.add_calls == [TMDB_MOVIE]
    assert [item["tmdb_id"] for item in mp.created] == [TMDB_MOVIE]
    async with session_factory() as other:
        sub = (await other.execute(select(Subscription).where(Subscription.id == resp.id))).scalar_one()
        assert sub.nf_subscribed is True
    assert await _system_logs(db_session) == [], "正常推送不得写跳过日志"
