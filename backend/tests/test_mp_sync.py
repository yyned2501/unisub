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

    async def get_missing_seasons(self, tmdb_id, media_type, title, year=None, seasons=None):
        # seasons 由 mp_sync 从本地/TMDB 取得后传入；桩直接返回配置的缺集结果
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


class FakeTmdb:
    """TMDBService 测试桩 — get_seasons_map / get_season_completion 返回可配置结果。"""

    def __init__(self, seasons_map=None, completion=None):
        # 默认给一个非空季集结构，使 mp_sync 的缺集查询流程能走下去
        self.seasons_map = seasons_map if seasons_map is not None else {1: [1, 2, 3]}
        # 每季是否已完结 {季号: bool}；默认空 → 所有季按未完结处理（保留订阅）
        self.completion = completion if completion is not None else {}
        self.calls: list[int] = []

    async def get_seasons_map(self, db, tmdb_id):
        self.calls.append(tmdb_id)
        return self.seasons_map

    async def get_season_completion(self, db, tmdb_id):
        return self.completion


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
    engine = MpSyncEngine(fake, FakeTmdb())
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
    engine = MpSyncEngine(fake, FakeTmdb())
    sub = _make_sub()
    db_session.add(sub)
    await db_session.flush()

    await engine.subscribe(db_session, sub)
    await db_session.commit()

    rows = (await db_session.execute(select(MpSubscription))).scalars().all()
    assert rows == []
    assert fake.created == []


async def test_subscribe_tv_skips_special_season_zero(db_session):
    """缺集季含特典季（season=0）时应跳过，不对其建订阅。"""
    fake = FakeMp()
    fake.missing_seasons = [
        {"season": 0, "episodes": [1], "total_episode": 5},  # 特典季，应跳过
        {"season": 1, "episodes": [3], "total_episode": 10},
    ]
    engine = MpSyncEngine(fake, FakeTmdb())
    sub = _make_sub()
    db_session.add(sub)
    await db_session.flush()

    await engine.subscribe(db_session, sub)
    await db_session.commit()

    rows = (await db_session.execute(select(MpSubscription))).scalars().all()
    assert [r.season for r in rows] == [1]  # 只有第 1 季，season=0 被跳过


async def test_subscribe_tv_query_failure_skips(db_session):
    """缺集查询失败（返回 error dict）时降级跳过，不建订阅。"""
    fake = FakeMp()
    fake.missing_seasons = {"error": "HTTP 500", "detail": "down"}
    engine = MpSyncEngine(fake, FakeTmdb())
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
    engine = MpSyncEngine(fake, FakeTmdb())
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
    engine = MpSyncEngine(fake, FakeTmdb())
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
    engine = MpSyncEngine(fake, FakeTmdb())
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
    """sync 应删除已完结且补齐（MP 不再缺集）的季订阅与子表行。"""
    fake = FakeMp()
    # 第 2 季已完结 → 补齐后应删；第 1 季仍缺集 → 保留
    engine = MpSyncEngine(fake, FakeTmdb(completion={1: False, 2: True}))
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


async def test_sync_keeps_unfinished_filled_season(db_session):
    """已订阅的季即便暂不缺集，只要未完结（后续还有集）就保留订阅，不删除。"""
    fake = FakeMp()
    # 第 2 季未完结 → 即便补齐也保留
    engine = MpSyncEngine(fake, FakeTmdb(completion={1: False, 2: False}))
    sub = _make_sub()
    db_session.add(sub)
    await db_session.flush()
    db_session.add(MpSubscription(subscription_id=sub.id, tmdb_id=sub.tmdb_id, season=1, mp_sub_id=501))
    db_session.add(MpSubscription(subscription_id=sub.id, tmdb_id=sub.tmdb_id, season=2, mp_sub_id=502))
    await db_session.commit()
    # 现在只有第 1 季缺集，第 2 季暂不缺集但未完结
    fake.missing_seasons = [{"season": 1, "episodes": [5], "total_episode": 10}]

    await engine.sync(db_session)

    rows = (await db_session.execute(select(MpSubscription))).scalars().all()
    assert sorted(r.season for r in rows) == [1, 2]  # 第 2 季保留
    assert fake.deleted == []  # 未删除任何订阅


def test_extract_sub_id_variants():
    """_extract_sub_id 应兼容多种 MP 响应形态。"""
    assert _extract_sub_id({"data": {"id": 5}}) == 5
    assert _extract_sub_id({"id": 9}) == 9
    assert _extract_sub_id([{"id": 3}]) == 3
    assert _extract_sub_id([]) is None
    assert _extract_sub_id(None) is None
    assert _extract_sub_id({"foo": "bar"}) is None
