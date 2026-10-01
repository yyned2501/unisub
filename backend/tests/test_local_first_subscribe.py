"""本地优先订阅契约测试 — 用户请求不等 NF/MP 上游。

契约（2026-10-01）：
- subscribe() 默认 defer_upstream=True：本地落库并 commit 后立即返回，
  不等 NF 建订阅（~1s）与 MP 镜像（实测 12~13s）。
- 上游推送在后台任务里做，失败不回滚本地订阅，由同步引擎兜底。
- 并发重复提交由唯一索引兜底 → 幂等返回已存在记录。
"""

from __future__ import annotations

import asyncio
import time

from sqlalchemy import select

from app.models.activity_log import ActivityLog
from app.models.subscription import Subscription
from app.services.orchestrator import OrchestratorService


class SlowNf:
    """NextFind 桩 — 记录调用，add 需可配延迟（模拟上游慢）。"""

    def __init__(self, delay: float = 0.0, result: dict | None = None):
        self.delay = delay
        self.result = result if result is not None else {"id": "nf-1"}
        self.add_calls: list[int] = []
        self.started = asyncio.Event()

    async def add_subscription(self, tmdb_id: int, media_type: str | None = None, title: str | None = None) -> dict:
        self.add_calls.append(tmdb_id)
        self.started.set()
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.result


class BoomNf:
    """NextFind 桩 — 调用即抛异常，验证后台任务不外抛。"""

    async def add_subscription(self, tmdb_id: int, media_type: str | None = None, title: str | None = None) -> dict:
        raise RuntimeError("nf down")


async def test_subscribe_returns_without_waiting_upstream(db_session, session_factory) -> None:
    """默认路径：subscribe() 不等上游，本地记录已 commit，nf_subscribed 初值为 False。"""
    nf = SlowNf(delay=5.0)
    orch = OrchestratorService(nf, session_factory=session_factory)

    t0 = time.perf_counter()
    resp = await orch.subscribe(db_session, tmdb_id=501, title="慢上游剧", media_type="tv")
    elapsed = time.perf_counter() - t0

    # 请求路径不得等那 5 秒上游
    assert elapsed < 1.0, f"subscribe 被上游阻塞了 {elapsed:.2f}s"
    assert resp.nf_subscribed is False

    # 本地记录已提交（独立会话可见 → 真的 commit 了）
    async with session_factory() as other:
        sub = (await other.execute(select(Subscription).where(Subscription.tmdb_id == 501))).scalar_one()
        assert sub.title == "慢上游剧"
        assert sub.nf_subscribed is False

    # 活动日志在请求路径内写入
    logs = (await db_session.execute(select(ActivityLog).where(ActivityLog.tmdb_id == 501))).scalars().all()
    assert any(log.action == "subscribe" for log in logs)

    # 后台任务最终完成上游推送
    errors = await orch.drain_upstream()
    assert errors == []
    assert nf.add_calls == [501]
    async with session_factory() as other:
        sub = (await other.execute(select(Subscription).where(Subscription.tmdb_id == 501))).scalar_one()
        assert sub.nf_subscribed is True
        assert sub.nf_sub_id == "nf-1"


async def test_upstream_failure_keeps_local_subscription(db_session, session_factory) -> None:
    """上游异常只记日志：本地订阅仍在，后台任务不把异常抛到事件循环。"""
    orch = OrchestratorService(BoomNf(), session_factory=session_factory)

    resp = await orch.subscribe(db_session, tmdb_id=502, title="上游炸剧", media_type="movie")
    errors = await orch.drain_upstream()

    assert errors == []  # 后台任务自吞异常
    assert await db_session.get(Subscription, resp.id) is not None


async def test_duplicate_insert_race_is_idempotent(db_session, session_factory, monkeypatch) -> None:
    """并发竞态：预检看不到对方未提交的行、INSERT 撞唯一索引 → 幂等返回已存在记录。

    模拟方式：让 subscribe 内的第一次 select 返回空（等价于另一个并发请求
    刚提交、本次预检发生在它提交之前），随后撞 ix_subscriptions_tmdb_id。
    """
    import uuid
    from datetime import UTC, datetime

    import app.services.orchestrator as orch_mod

    real_select = orch_mod.select
    state = {"calls": 0}

    def racing_select(*args, **kwargs):
        state["calls"] += 1
        if state["calls"] == 1:  # 等价于"预检发生在另一个并发请求提交之前"：查不到任何行
            return real_select(Subscription).where(Subscription.tmdb_id == -1)
        return real_select(*args, **kwargs)

    existing_id = str(uuid.uuid4())
    async with session_factory() as other:  # 模拟并发请求已提交的那条记录
        other.add(
            Subscription(
                id=existing_id,
                tmdb_id=503,
                media_type="tv",
                title="并发剧",
                source="forward",
                nf_subscribed=False,
                nf_missing_eps=0,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        await other.commit()

    orch = OrchestratorService(SlowNf(), session_factory=session_factory)
    monkeypatch.setattr(orch_mod, "select", racing_select)

    resp = await orch.subscribe(db_session, tmdb_id=503, title="并发剧", media_type="tv")
    await orch.drain_upstream()

    assert resp.id == existing_id, "撞唯一索引时应返回已存在记录，而不是新增一条"
    rows = (await db_session.execute(select(Subscription).where(Subscription.tmdb_id == 503))).scalars().all()
    assert len(rows) == 1
    assert orch._upstream_tasks == set()


async def test_inline_mode_pushes_upstream_before_return(db_session) -> None:
    """defer_upstream=False：内联推送上游，返回时 nf_subscribed 已是 True（确定性调用方）。"""
    nf = SlowNf()
    orch = OrchestratorService(nf)

    resp = await orch.subscribe(db_session, tmdb_id=504, title="内联剧", media_type="tv", defer_upstream=False)

    assert resp.nf_subscribed is True
    assert resp.nf_sub_id == "nf-1"
    assert nf.add_calls == [504]
    assert orch._upstream_tasks == set()
