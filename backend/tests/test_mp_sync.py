"""MpSyncEngine 测试 — MP 镜像订阅的正向与异常路径。

用 FakeMp 桩替换 MoviePilotService，用内存 sqlite 会话验证子表读写。
"""

from sqlalchemy import select

from app.models.mp_subscription import MpSubscription
from app.models.subscription import Subscription
from app.services.mp_sync import MpSyncEngine, _extract_sub_id


class FakeMp:
    """MoviePilotService 测试桩 — 可配置各接口返回值并记录调用。"""

    def __init__(self):
        self.missing_seasons: list[dict] | dict = []
        self.create_result: dict = {"success": True, "data": {"id": 100}}
        self.find_result = None
        self.detail_result: dict = {"state": "R", "total_episode": 10, "lack_episode": 3, "completed_episode": 7}
        self.delete_result: dict = {}
        self.created: list[dict] = []
        self.deleted: list[int] = []

    async def get_missing_seasons(self, tmdb_id, media_type, title, year=None):
        return self.missing_seasons

    async def create_subscription(self, tmdb_id, media_type, title, year=None, season=None):
        self.created.append({"tmdb_id": tmdb_id, "season": season})
        return self.create_result

    async def find_subscription(self, tmdb_id, season=None):
        return self.find_result

    async def get_subscription_detail(self, mp_sub_id):
        return self.detail_result

    async def delete_subscription(self, mp_sub_id):
        self.deleted.append(mp_sub_id)
        return self.delete_result


def _make_sub(media_type: str = "tv", **kw) -> Subscription:
    """构造一个本地订阅记录。"""
    return Subscription(
        id="sub-1",
        tmdb_id=123,
        media_type=media_type,
        title="测试剧",
        year=2024,
        nf_subscribed=True,
        **kw,
    )


async def test_subscribe_tv_creates_per_missing_season(db_session):
    """电视剧应按缺集季逐季创建 MP 订阅并写入子表。"""
    fake = FakeMp()
    fake.missing_seasons = [
        {"season": 1, "episodes": [3, 4], "total_episode": 10},
        {"season": 2, "episodes": [1], "total_episode": 8},
    ]
    engine = MpSyncEngine(fake)
    sub = _make_sub()
    db_session.add(sub)
    await db_session.flush()

    await engine.subscribe(db_session, sub)
    await db_session.commit()

    rows = (await db_session.execute(select(MpSubscription))).scalars().all()
    assert len(rows) == 2
    seasons = sorted(r.season for r in rows)
    assert seasons == [1, 2]
    assert len(fake.created) == 2


async def test_subscribe_tv_no_missing_seasons_skips(db_session):
    """剧集无缺集季时不创建 MP 订阅。"""
    fake = FakeMp()
    fake.missing_seasons = []
    engine = MpSyncEngine(fake)
    sub = _make_sub()
    db_session.add(sub)
    await db_session.flush()

    await engine.subscribe(db_session, sub)
    await db_session.commit()

    rows = (await db_session.execute(select(MpSubscription))).scalars().all()
    assert rows == []
    assert fake.created == []


async def test_subscribe_tv_query_failure_skips(db_session):
    """缺集查询失败（返回 error dict）时降级跳过，不建订阅。"""
    fake = FakeMp()
    fake.missing_seasons = {"error": "HTTP 500", "detail": "down"}
    engine = MpSyncEngine(fake)
    sub = _make_sub()
    db_session.add(sub)
    await db_session.flush()

    await engine.subscribe(db_session, sub)
    await db_session.commit()

    rows = (await db_session.execute(select(MpSubscription))).scalars().all()
    assert rows == []


async def test_subscribe_movie_creates_single_no_season(db_session):
    """电影应创建一条 season 为 NULL 的 MP 订阅。"""
    fake = FakeMp()
    engine = MpSyncEngine(fake)
    sub = _make_sub(media_type="movie")
    db_session.add(sub)
    await db_session.flush()

    await engine.subscribe(db_session, sub)
    await db_session.commit()

    rows = (await db_session.execute(select(MpSubscription))).scalars().all()
    assert len(rows) == 1
    assert rows[0].season is None
    assert rows[0].mp_sub_id == 100


async def test_unsubscribe_deletes_all_rows(db_session):
    """取消订阅应删除 MP 端订阅并清空子表行。"""
    fake = FakeMp()
    engine = MpSyncEngine(fake)
    sub = _make_sub()
    db_session.add(sub)
    await db_session.flush()
    for sn in (1, 2):
        db_session.add(
            MpSubscription(
                subscription_id=sub.id,
                tmdb_id=sub.tmdb_id,
                season=sn,
                mp_sub_id=200 + sn,
            )
        )
    await db_session.commit()

    await engine.unsubscribe(db_session, sub)
    await db_session.commit()

    rows = (await db_session.execute(select(MpSubscription))).scalars().all()
    assert rows == []
    assert sorted(fake.deleted) == [201, 202]


async def test_sync_refreshes_progress_and_adds_new_season(db_session):
    """sync 应回写存量季进度，并为新出现的缺集季建订阅。"""
    fake = FakeMp()
    engine = MpSyncEngine(fake)
    sub = _make_sub()
    db_session.add(sub)
    await db_session.flush()
    # 存量：第 1 季已建 MP 订阅
    db_session.add(MpSubscription(subscription_id=sub.id, tmdb_id=sub.tmdb_id, season=1, mp_sub_id=301))
    await db_session.commit()
    # 现在 MP 报告第 1、2 季都缺集
    fake.missing_seasons = [
        {"season": 1, "episodes": [5], "total_episode": 10},
        {"season": 2, "episodes": [1, 2], "total_episode": 8},
    ]

    await engine.sync(db_session)

    rows = (await db_session.execute(select(MpSubscription))).scalars().all()
    by_season = {r.season: r for r in rows}
    assert set(by_season) == {1, 2}
    # 存量季进度已回写
    assert by_season[1].mp_status == "R"
    assert by_season[1].mp_missing_eps == 3
    assert by_season[1].mp_completed_eps == 7
    # 新季已建订阅
    assert by_season[2].mp_sub_id == 100


async def test_sync_removes_filled_season(db_session):
    """sync 应删除已补齐（MP 不再缺集）的季订阅与子表行。"""
    fake = FakeMp()
    engine = MpSyncEngine(fake)
    sub = _make_sub()
    db_session.add(sub)
    await db_session.flush()
    db_session.add(MpSubscription(subscription_id=sub.id, tmdb_id=sub.tmdb_id, season=1, mp_sub_id=401))
    db_session.add(MpSubscription(subscription_id=sub.id, tmdb_id=sub.tmdb_id, season=2, mp_sub_id=402))
    await db_session.commit()
    # 现在只有第 1 季缺集，第 2 季已补齐
    fake.missing_seasons = [{"season": 1, "episodes": [5], "total_episode": 10}]

    await engine.sync(db_session)

    rows = (await db_session.execute(select(MpSubscription))).scalars().all()
    assert [r.season for r in rows] == [1]
    assert fake.deleted == [402]


def test_extract_sub_id_variants():
    """_extract_sub_id 应兼容多种 MP 响应形态。"""
    assert _extract_sub_id({"data": {"id": 5}}) == 5
    assert _extract_sub_id({"id": 9}) == 9
    assert _extract_sub_id([{"id": 3}]) == 3
    assert _extract_sub_id([]) is None
    assert _extract_sub_id(None) is None
    assert _extract_sub_id({"foo": "bar"}) is None
