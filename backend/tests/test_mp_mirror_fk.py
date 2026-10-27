"""回归测试 — 订阅镜像（mp_subscription）的入库顺序与 best-effort 契约。

背景（生产事故 2026-10-01）：从 forward 端点订阅电影（剧场版）必失败。

    ForeignKeyViolationError: insert or update on table "mp_subscription"
    violates foreign key constraint "mp_subscription_subscription_id_fkey"

根因：Subscription 与 MpSubscription 之间只有裸 FK 列、没有 relationship()，
SQLAlchemy 的工作单元只按关系排序 INSERT、不按 FK 排序。电影分支
（MpSyncEngine.subscribe → _create_mp_sub）中间没有任何 DB 查询，父表
subscriptions 一直是 pending，commit 时子表 INSERT 先发出 → 撞 FK。
电视剧分支因为在中间调了 query_missing_seasons()（一次 SELECT 触发
autoflush，父表提前落库）而侥幸通过。

这两条测试在修复前必挂（sqlite 已开 PRAGMA foreign_keys=ON，行为与 PG 一致）。
"""

import pytest
from sqlalchemy import event, select

from app.models.mp_subscription import MpSubscription
from app.models.subscription import Subscription
from app.services.orchestrator.service import OrchestratorService
from tests.conftest import _test_engine


# 测试库默认不校验外键（sqlite 的 PRAGMA foreign_keys 默认 OFF），
# 打开它才能让「父行缺失」这类缺陷在测试里暴露，与生产 PG 行为对齐。
@event.listens_for(_test_engine.sync_engine, "connect")
def _enable_sqlite_fk(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TMDB_MOVIE = 1599191  # 仙逆剧场版：弑仙之战
TITLE = "仙逆剧场版：弑仙之战"


class FakeNf:
    """NextFindService 测试桩 — 永远订阅成功。"""

    def __init__(self):
        self.add_calls: list[int] = []

    async def add_subscription(self, tmdb_id, media_type=None, title=None):
        self.add_calls.append(tmdb_id)
        return {"id": "nf-100"}


class FakeMpOk:
    """MoviePilotService 测试桩 — 建订阅成功，返回 mp_sub_id=2256。"""

    def __init__(self):
        self.created: list[dict] = []

    async def find_subscription(self, tmdb_id, season=None):
        return None

    async def create_subscription(self, tmdb_id, media_type, title, year=None, season=None):
        self.created.append({"tmdb_id": tmdb_id, "season": season})
        return {"success": True, "data": {"id": 2256}}


class FakeMpBoom:
    """MoviePilotService 测试桩 — 建订阅直接抛异常（模拟 MP 侧故障）。"""

    async def find_subscription(self, tmdb_id, season=None):
        raise RuntimeError("MP 连接超时（模拟）")


async def test_movie_subscribe_writes_mirror_row(db_session):
    """电影订阅：本地父行 + MP 镜像子行都必须落库。"""
    nf, mp = FakeNf(), FakeMpOk()
    svc = OrchestratorService(nf_service=nf, mp_service=mp, tmdb_service=None)

    await svc.subscribe(
        db_session,
        tmdb_id=TMDB_MOVIE,
        title=TITLE,
        media_type="movie",
        year=2026,
        source="forward",
        defer_upstream=False,
    )

    sub = (await db_session.execute(select(Subscription).where(Subscription.tmdb_id == TMDB_MOVIE))).scalar_one()
    rows = (
        (await db_session.execute(select(MpSubscription).where(MpSubscription.tmdb_id == TMDB_MOVIE))).scalars().all()
    )

    assert len(rows) == 1, "电影订阅必须留下一条 MP 镜像"
    assert rows[0].subscription_id == sub.id, "镜像的 subscription_id 必须指向本地订阅"
    assert rows[0].season is None, "电影镜像 season 必须为 NULL"
    assert rows[0].mp_sub_id == 2256


async def test_mirror_failure_does_not_lose_subscription(db_session):
    """镜像写入失败 = best-effort：只记日志，绝不回滚用户订阅。

    契约写在 MpSyncEngine 的 docstring 里，实现曾经共享主事务，
    镜像是异常时连 subscriptions 父行一起回滚（用户订阅凭空消失）。
    """
    nf = FakeNf()
    svc = OrchestratorService(nf_service=nf, mp_service=FakeMpBoom(), tmdb_service=None)

    # 必须正常返回，不能把 MP 的故障抛给调用方
    await svc.subscribe(
        db_session,
        tmdb_id=TMDB_MOVIE,
        title=TITLE,
        media_type="movie",
        year=2026,
        source="forward",
        defer_upstream=False,
    )

    sub = (
        await db_session.execute(select(Subscription).where(Subscription.tmdb_id == TMDB_MOVIE))
    ).scalar_one_or_none()
    assert sub is not None, "MP 镜像失败不得回滚本地订阅"
    assert sub.nf_subscribed is True

    rows = (
        (await db_session.execute(select(MpSubscription).where(MpSubscription.tmdb_id == TMDB_MOVIE))).scalars().all()
    )
    assert rows == [], "镜像失败不应留下半成品行"


@pytest.mark.parametrize("media_type", ["movie", "tv"])
async def test_subscription_survives_when_mirror_disabled(db_session, media_type):
    """未配置 MP 时（_mp_sync 为 None）订阅仍应正常写入。"""
    svc = OrchestratorService(nf_service=FakeNf(), mp_service=None, tmdb_service=None)

    await svc.subscribe(
        db_session,
        tmdb_id=TMDB_MOVIE + 1,
        title="无 MP 配置的订阅",
        media_type=media_type,
        source="forward",
        defer_upstream=False,
    )

    sub = (
        await db_session.execute(select(Subscription).where(Subscription.tmdb_id == TMDB_MOVIE + 1))
    ).scalar_one_or_none()
    assert sub is not None
