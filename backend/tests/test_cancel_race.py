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
from app.models.mp_subscription import MpSubscription
from app.models.subscription import Subscription
from app.services.orchestrator.service import OrchestratorService

TITLE = "盗梦空间"
TMDB_MOVIE = 27205
SKIP_MARK = "订阅已取消，跳过上游推送"
REVOKE_MARK = "撤销刚建的上游订阅"


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
    """MoviePilot 桩 — 记录建订阅/删订阅调用（僵尸订阅就是在这里被建出来的）。"""

    def __init__(self, gate: asyncio.Event | None = None):
        self.gate = gate
        self.created: list[dict] = []
        self.deleted: list[int] = []
        self.entered = asyncio.Event()

    async def find_subscription(self, tmdb_id: int, season: int | None = None):
        return None

    async def create_subscription(
        self, tmdb_id: int, media_type: str, title: str, year: int | None = None, season: int | None = None
    ) -> dict:
        self.created.append({"tmdb_id": tmdb_id, "season": season})
        self.entered.set()
        if self.gate is not None:
            await self.gate.wait()  # 卡住：由测试在「取消」之后放行（复现 12~15s 出网窗口）
        return {"success": True, "data": {"id": 9999}}

    async def delete_subscription(self, mp_sub_id: int) -> dict:
        self.deleted.append(mp_sub_id)
        return {"success": True}


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


async def test_cancel_during_nf_push_revokes_nf_subscription(db_session, session_factory) -> None:
    """取消落在 NF 推送出网窗口内：已发出去的 NF 订阅必须在返回后被撤销（§8.3-B）。

    取消路径自己也调了 NF remove（用户 API 层取消先同步等 NF）；但本任务的 add 可能
    落在它之后才建出来，所以补偿那次 remove 是必需的 —— 断言补偿恰好 1 次。
    """
    gate = asyncio.Event()
    nf, mp = FakeNfCancel(gate=gate), FakeMpMirror()
    orch = OrchestratorService(nf, mp, session_factory=session_factory)

    resp = await orch.subscribe(db_session, tmdb_id=TMDB_MOVIE, title=TITLE, media_type="movie")
    await asyncio.wait_for(nf.entered.wait(), timeout=5)

    result = await orch.unsubscribe(db_session, resp.id)
    assert result["success"] is True
    removes_by_cancel = len(nf.remove_calls)  # 取消路径自己的 remove，不算补偿

    gate.set()  # 放行 NF 调用，让后台任务继续跑
    errors = await orch.drain_upstream()
    assert errors == []

    assert len(nf.remove_calls) == removes_by_cancel + 1, "出网窗口内建的那条 NF 订阅必须被撤销，且只撤一次"
    assert mp.created == [], "NF 窗口内的取消不得再进 MP 镜像"
    logs = await _system_logs(db_session)
    assert any(REVOKE_MARK in message and "NF" in message for message in logs), f"缺少补偿撤销日志: {logs}"


async def test_cancel_during_mp_mirror_revokes_created_mp_sub(db_session, session_factory) -> None:
    """取消落在 MP 镜像出网窗口内（生产 12~15s 窗口）：补偿撤掉刚建的那条 MP 订阅。

    这是 §8.3-B 的核心场景，也是生产 mp_sub_id=2263 僵尸订阅的成因：本地行在
    「NF 已推送、MP 正在建订阅」时被删。A2 守卫只挡得住「进 MP 之前」的取消，
    窗口内漏出去的这条必须在调用返回后撤销 —— 只记日志不算修好。
    """
    gate = asyncio.Event()
    nf, mp = FakeNfCancel(), FakeMpMirror(gate=gate)
    orch = OrchestratorService(nf, mp, session_factory=session_factory)

    resp = await orch.subscribe(db_session, tmdb_id=TMDB_MOVIE, title=TITLE, media_type="movie")
    await asyncio.wait_for(mp.entered.wait(), timeout=5)

    # 取消（真实取消路径）—— 此刻 MP 那条还没落本地子表，取消路径看不见它，撤不掉
    result = await orch.unsubscribe(db_session, resp.id)
    assert result["success"] is True

    gate.set()  # 放行 MP 建订阅，让后台任务继续跑
    errors = await orch.drain_upstream()
    assert errors == []

    assert [item["tmdb_id"] for item in mp.created] == [TMDB_MOVIE], "出网窗口内确实建出来了（所以必须补偿）"
    assert mp.deleted == [9999], "出网窗口内建的那条 MP 订阅必须被撤销（只记日志不算修好）"
    # §8.3-B「NF/MP 各撤一次」：取消路径的 remove 可能早于本任务的 NF 建订阅落地
    # （真机实测 NF 侧残留，见 t_8af09354），补偿必须再撤一次（有界、幂等）。
    assert nf.remove_calls == [TMDB_MOVIE, TMDB_MOVIE], "NF 侧补偿必须再撤一次（取消路径那次不算）"
    logs = await _system_logs(db_session)
    assert any(REVOKE_MARK in message and "MP:9999" in message for message in logs), f"缺少补偿撤销日志: {logs}"

    # 父行已删，镜像的子表写入必须被回滚（不得留孤儿行）
    async with session_factory() as other:
        assert (await other.execute(select(MpSubscription))).scalars().all() == []


class FakeMpTimeoutButCreated:
    """MP 桩 — 建订阅「报告失败」但上游其实建出来了（真机 mp_sub_id=2268 的成因）。

    2026-10-02 真机：冷门片建订阅超过客户端 30s 超时 → 返回 request_failed，
    但 MP 侧已经建好 → unisub 无记录、无本地镜像的上游僵尸订阅。客户端报错后
    必须复扫一次，把这条按「本次新建」认领下来，取消补偿才撤得掉。
    """

    def __init__(self, gate: asyncio.Event, mp_sub_id: int = 2268):
        self.gate = gate
        self.mp_sub_id = mp_sub_id
        self.find_calls = 0
        self.created: list[int] = []
        self.deleted: list[int] = []
        self.entered = asyncio.Event()

    async def find_subscription(self, tmdb_id: int, season: int | None = None):
        self.find_calls += 1
        if self.find_calls == 1:  # 建之前的防重查询：MP 侧还没有
            return None
        return {"id": self.mp_sub_id, "tmdbid": tmdb_id, "season": season}

    async def create_subscription(
        self, tmdb_id: int, media_type: str, title: str, year: int | None = None, season: int | None = None
    ) -> dict:
        self.created.append(tmdb_id)
        self.entered.set()
        await self.gate.wait()  # 卡住：复现「出网 30s 超时」窗口
        return {"error": "request_failed", "detail": ""}

    async def delete_subscription(self, mp_sub_id: int) -> dict:
        self.deleted.append(mp_sub_id)
        return {"success": True}


async def test_mp_create_reported_failure_but_created_is_claimed(db_session, session_factory) -> None:
    """客户端报「建订阅失败」但 MP 侧已建 → 必须复扫认领并写本地镜像（不留僵尸）。"""
    nf, mp = FakeNfCancel(), FakeMpTimeoutButCreated(gate=asyncio.Event())
    mp.gate.set()  # 不阻塞：直接走「报错 + 复扫」分支
    orch = OrchestratorService(nf, mp, session_factory=session_factory)

    resp = await orch.subscribe(db_session, tmdb_id=TMDB_MOVIE, title=TITLE, media_type="movie")
    errors = await orch.drain_upstream()
    assert errors == []

    async with session_factory() as other:
        rows = (await other.execute(select(MpSubscription))).scalars().all()
    assert [row.mp_sub_id for row in rows] == [2268], "报错但上游已建的订阅必须被本地记录（否则是僵尸）"
    assert rows[0].subscription_id == resp.id


async def test_cancel_during_failed_mp_create_revokes_orphan(db_session, session_factory) -> None:
    """取消落在「报错但已建」的出网窗口内 → 这条 MP 订阅也必须被撤销（真机 2268 场景）。"""
    gate = asyncio.Event()
    nf, mp = FakeNfCancel(), FakeMpTimeoutButCreated(gate=gate)
    orch = OrchestratorService(nf, mp, session_factory=session_factory)

    resp = await orch.subscribe(db_session, tmdb_id=TMDB_MOVIE, title=TITLE, media_type="movie")
    await asyncio.wait_for(mp.entered.wait(), timeout=5)

    result = await orch.unsubscribe(db_session, resp.id)
    assert result["success"] is True

    gate.set()  # 放行：建订阅以 request_failed 返回，但 MP 侧其实已建
    errors = await orch.drain_upstream()
    assert errors == []

    assert mp.created == [TMDB_MOVIE], "出网窗口内确实发出过建订阅"
    assert mp.deleted == [2268], "报错但上游已建的那条必须被撤销，不得留僵尸"
    logs = await _system_logs(db_session)
    assert any(REVOKE_MARK in message and "MP:2268" in message for message in logs), f"缺少补偿撤销日志: {logs}"
    async with session_factory() as other:
        assert (await other.execute(select(MpSubscription))).scalars().all() == []
