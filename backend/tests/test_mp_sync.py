"""MpSyncEngine 测试 — MP 镜像订阅的正向与异常路径。

缺集判断已改为本地计算（tmdb_season 已播 - emby_season_cache 库内），故测试用
FakeTmdb.seasons_map（已播结构）+ 库中 EmbySeasonCache 行（库内集数）驱动缺集结果；
FakeMp.get_missing_seasons 仅在「剧在库但无按季缓存」的兜底路径生效。
"""

from sqlalchemy import select

from app.models.emby_cache import EmbyCache
from app.models.emby_season_cache import EmbySeasonCache
from app.models.mp_subscription import MpSubscription
from app.models.subscription import Subscription
from app.services.mp_sync import MpSyncEngine, _extract_sub_id


class FakeMp:
    """MoviePilotService 测试桩 — get_missing_seasons 仅兜底路径用到。"""

    def __init__(self):
        self.missing_seasons: list[dict] | dict = []
        self.create_result: dict = {"success": True, "data": {"id": 100}}
        self.find_result = None
        self.detail_result: dict = {"state": "R", "total_episode": 10, "lack_episode": 3, "completed_episode": 7}
        self.delete_result: dict = {}
        self.created: list[dict] = []
        self.deleted: list[int] = []
        self.notexists_calls = 0

    async def get_missing_seasons(self, tmdb_id, media_type, title, year=None, seasons=None):
        self.notexists_calls += 1
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
        self.seasons_map = seasons_map if seasons_map is not None else {1: [1, 2, 3]}
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


def _seed_emby_seasons(db, tmdb_id: int, counts: dict[int, int]) -> None:
    """在 emby_season_cache 写入按季库内集数。"""
    for sn, cnt in counts.items():
        db.add(EmbySeasonCache(tmdb_id=tmdb_id, season=sn, episode_count=cnt))


def _seed_emby_show(db, tmdb_id: int) -> None:
    """在 emby_cache 写入一条记录，表示剧在 Emby 库中。"""
    db.add(EmbyCache(tmdb_id=tmdb_id, emby_series_name="测试剧"))


async def test_subscribe_tv_local_missing_creates_per_season(db_session):
    """本地算缺集：已播 > 库内的季逐季建 MP 订阅，不调 notexists。"""
    fake = FakeMp()
    # 已播：第1季3集、第2季2集；库内：第1季1集 → 第1季缺2、第2季缺2（库内0）
    _seed_emby_seasons(db_session, 123, {1: 1})
    engine = MpSyncEngine(fake, FakeTmdb(seasons_map={1: [1, 2, 3], 2: [1, 2]}))
    sub = _make_sub()
    db_session.add(sub)
    await db_session.flush()

    await engine.subscribe(db_session, sub)
    await db_session.commit()

    rows = (await db_session.execute(select(MpSubscription))).scalars().all()
    assert sorted(r.season for r in rows) == [1, 2]
    assert len(fake.created) == 2
    assert fake.notexists_calls == 0  # 走本地，未调 notexists


async def test_subscribe_tv_season_full_not_subscribed(db_session):
    """库内集数 >= 已播的季不缺集，不建订阅。"""
    fake = FakeMp()
    _seed_emby_seasons(db_session, 123, {1: 3, 2: 2})  # 两季都已补齐
    engine = MpSyncEngine(fake, FakeTmdb(seasons_map={1: [1, 2, 3], 2: [1, 2]}))
    sub = _make_sub()
    db_session.add(sub)
    await db_session.flush()

    await engine.subscribe(db_session, sub)
    await db_session.commit()

    rows = (await db_session.execute(select(MpSubscription))).scalars().all()
    assert rows == []
    assert fake.created == []


async def test_subscribe_tv_not_in_emby_skips(db_session):
    """剧不在 Emby 库（无 emby_cache）→ 不镜像（只补已在库剧的缺集），不建订阅。"""
    fake = FakeMp()
    engine = MpSyncEngine(fake, FakeTmdb(seasons_map={1: [1, 2, 3], 2: [1]}))
    sub = _make_sub()
    db_session.add(sub)
    await db_session.flush()

    await engine.subscribe(db_session, sub)
    await db_session.commit()

    rows = (await db_session.execute(select(MpSubscription))).scalars().all()
    assert rows == []
    assert fake.created == []
    assert fake.notexists_calls == 0


async def test_subscribe_tv_sync_gap_falls_back_to_notexists(db_session):
    """剧在库但无按季缓存（同步缺口）→ 回退 notexists 兜底一次。"""
    fake = FakeMp()
    fake.missing_seasons = [{"season": 1, "episodes": [3], "total_episode": 3}]
    _seed_emby_show(db_session, 123)  # 在库，但无 emby_season_cache
    engine = MpSyncEngine(fake, FakeTmdb(seasons_map={1: [1, 2, 3]}))
    sub = _make_sub()
    db_session.add(sub)
    await db_session.flush()

    await engine.subscribe(db_session, sub)
    await db_session.commit()

    assert fake.notexists_calls == 1  # 触发了兜底
    rows = (await db_session.execute(select(MpSubscription))).scalars().all()
    assert [r.season for r in rows] == [1]


async def test_subscribe_tv_fallback_failure_skips(db_session):
    """兜底 notexists 失败时降级跳过，不建订阅。"""
    fake = FakeMp()
    fake.missing_seasons = {"error": "HTTP 502", "detail": "down"}
    _seed_emby_show(db_session, 123)
    engine = MpSyncEngine(fake, FakeTmdb(seasons_map={1: [1, 2, 3]}))
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
    # 剧在 Emby 库；库内第1季1集（缺2）、第2季无记录（缺）→ 两季都缺
    _seed_emby_show(db_session, 123)
    _seed_emby_seasons(db_session, 123, {1: 1})
    engine = MpSyncEngine(fake, FakeTmdb(seasons_map={1: [1, 2, 3], 2: [1, 2]}))
    sub = _make_sub()
    db_session.add(sub)
    await db_session.flush()
    db_session.add(MpSubscription(subscription_id=sub.id, tmdb_id=sub.tmdb_id, season=1, mp_sub_id=301))
    await db_session.commit()

    await engine.sync(db_session)

    rows = (await db_session.execute(select(MpSubscription))).scalars().all()
    by_season = {r.season: r for r in rows}
    assert set(by_season) == {1, 2}
    assert by_season[1].mp_status == "R"
    assert by_season[1].mp_missing_eps == 3
    assert by_season[1].mp_completed_eps == 7
    assert by_season[2].mp_sub_id == 100


async def test_sync_removes_filled_season(db_session):
    """sync 应删除已完结且补齐（库内 >= 已播）的季订阅与子表行。"""
    fake = FakeMp()
    # 库内：第2季已补齐（2集）；第1季无库内记录 → 缺。第2季完结 → 删
    _seed_emby_show(db_session, 123)
    _seed_emby_seasons(db_session, 123, {2: 2})
    engine = MpSyncEngine(fake, FakeTmdb(seasons_map={1: [1, 2, 3], 2: [1, 2]}, completion={1: False, 2: True}))
    sub = _make_sub()
    db_session.add(sub)
    await db_session.flush()
    db_session.add(MpSubscription(subscription_id=sub.id, tmdb_id=sub.tmdb_id, season=1, mp_sub_id=401))
    db_session.add(MpSubscription(subscription_id=sub.id, tmdb_id=sub.tmdb_id, season=2, mp_sub_id=402))
    await db_session.commit()

    await engine.sync(db_session)

    rows = (await db_session.execute(select(MpSubscription))).scalars().all()
    assert [r.season for r in rows] == [1]
    assert fake.deleted == [402]


async def test_sync_keeps_unfinished_filled_season(db_session):
    """已订阅的季即便补齐，只要未完结就保留订阅，不删除。"""
    fake = FakeMp()
    _seed_emby_show(db_session, 123)
    _seed_emby_seasons(db_session, 123, {2: 2})  # 第2季补齐但未完结
    engine = MpSyncEngine(fake, FakeTmdb(seasons_map={1: [1, 2, 3], 2: [1, 2]}, completion={1: False, 2: False}))
    sub = _make_sub()
    db_session.add(sub)
    await db_session.flush()
    db_session.add(MpSubscription(subscription_id=sub.id, tmdb_id=sub.tmdb_id, season=1, mp_sub_id=501))
    db_session.add(MpSubscription(subscription_id=sub.id, tmdb_id=sub.tmdb_id, season=2, mp_sub_id=502))
    await db_session.commit()

    await engine.sync(db_session)

    rows = (await db_session.execute(select(MpSubscription))).scalars().all()
    assert sorted(r.season for r in rows) == [1, 2]  # 第2季保留
    assert fake.deleted == []


async def test_sync_cleans_not_in_emby_show(db_session):
    """剧不在 Emby 库（如被移除）→ sync 应清掉其全部 MP 镜像订阅。"""
    fake = FakeMp()
    engine = MpSyncEngine(fake, FakeTmdb(seasons_map={1: [1, 2, 3]}))
    sub = _make_sub()
    db_session.add(sub)
    await db_session.flush()
    db_session.add(MpSubscription(subscription_id=sub.id, tmdb_id=sub.tmdb_id, season=1, mp_sub_id=601))
    db_session.add(MpSubscription(subscription_id=sub.id, tmdb_id=sub.tmdb_id, season=2, mp_sub_id=602))
    await db_session.commit()
    # 无 emby_cache 记录 → 剧不在库

    await engine.sync(db_session)

    rows = (await db_session.execute(select(MpSubscription))).scalars().all()
    assert rows == []
    assert sorted(fake.deleted) == [601, 602]


def test_extract_sub_id_variants():
    """_extract_sub_id 应兼容多种 MP 响应形态。"""
    assert _extract_sub_id({"data": {"id": 5}}) == 5
    assert _extract_sub_id({"id": 9}) == 9
    assert _extract_sub_id([{"id": 3}]) == 3
    assert _extract_sub_id([]) is None
    assert _extract_sub_id(None) is None
    assert _extract_sub_id({"foo": "bar"}) is None
