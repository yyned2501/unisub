"""TMDB 季集缓存测试 — save_seasons 写库与 get_seasons_map 本地/补缓存逻辑。"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.tmdb_season import TmdbSeason
from app.services.tmdb import TMDBService
from app.services.tmdb_cache import save_seasons
from app.services.tmdb_detail import aired_count_by_season


def _make_service() -> TMDBService:
    """构造测试用 TMDB 服务（api_key 占位，测试中 mock 网络调用）。"""
    return TMDBService("fake-key")


async def test_save_seasons_writes_rows_skip_special(db_session):
    """save_seasons 应按季写库，跳过特典季（season_number=0）。"""
    detail = {
        "seasons": [
            {"season_number": 0, "episode_count": 5},  # 特典季，应跳过
            {"season_number": 1, "episode_count": 12, "air_date": "2022-10-03"},
            {"season_number": 2, "episode_count": 10, "air_date": "2023-10-01"},
        ]
    }
    await save_seasons(db_session, 209311, detail)

    rows = (await db_session.execute(select(TmdbSeason).where(TmdbSeason.tmdb_id == 209311))).scalars().all()
    seasons = sorted(r.season for r in rows)
    assert seasons == [1, 2]  # 特典季 0 未入库
    by_season = {r.season: r for r in rows}
    assert by_season[1].episode_count == 12
    assert by_season[1].air_date == "2022-10-03"
    assert by_season[2].episode_count == 10
    # 无 status 且 air_date 在过去 → 视为已全部播出，aired_count = episode_count
    assert by_season[1].aired_count == 12
    assert by_season[2].aired_count == 10


async def test_save_seasons_updates_existing(db_session):
    """已存在的季应更新 episode_count，而非重复插入。"""
    db_session.add(TmdbSeason(tmdb_id=100, season=1, episode_count=5))
    await db_session.flush()

    await save_seasons(db_session, 100, {"seasons": [{"season_number": 1, "episode_count": 8}]})
    await db_session.flush()

    rows = (await db_session.execute(select(TmdbSeason).where(TmdbSeason.tmdb_id == 100))).scalars().all()
    assert len(rows) == 1
    assert rows[0].episode_count == 8


async def test_get_seasons_map_local_hit(db_session, monkeypatch):
    """本地有缓存时直接返回，不调 TMDB API。集数范围以 aired_count 为准。"""
    db_session.add(TmdbSeason(tmdb_id=200, season=1, episode_count=3, aired_count=3))
    db_session.add(TmdbSeason(tmdb_id=200, season=2, episode_count=2, aired_count=2))
    await db_session.commit()

    called = {"hit": False}

    async def fake_update(self, db, tmdb_id):
        called["hit"] = True
        return None

    monkeypatch.setattr(TMDBService, "update_cache_for_tv", fake_update)
    svc = _make_service()
    result = await svc.get_seasons_map(db_session, 200)

    assert result == {1: [1, 2, 3], 2: [1, 2]}
    assert called["hit"] is False  # 本地命中（已播季，无需 TTL 刷新），未调 TMDB


async def test_get_seasons_map_local_miss_triggers_tmdb(db_session, monkeypatch):
    """本地无缓存时应调 update_cache_for_tv 补数据后再返回。"""

    async def fake_update(self, db, tmdb_id):
        # 模拟调 TMDB 后写入季数据（air_date 在过去 → 已播 4 集）
        await save_seasons(
            db, tmdb_id, {"seasons": [{"season_number": 1, "episode_count": 4, "air_date": "2020-01-01"}]}
        )
        await db.commit()
        return {"tmdb_total_eps": 4}

    monkeypatch.setattr(TMDBService, "update_cache_for_tv", fake_update)
    svc = _make_service()
    result = await svc.get_seasons_map(db_session, 300)

    assert result == {1: [1, 2, 3, 4]}


async def test_get_seasons_map_no_data_returns_none(db_session, monkeypatch):
    """TMDB 也查不到季数据时返回 None。"""

    async def fake_update(self, db, tmdb_id):
        return None  # TMDB 查询失败

    monkeypatch.setattr(TMDBService, "update_cache_for_tv", fake_update)
    svc = _make_service()
    result = await svc.get_seasons_map(db_session, 999)
    assert result is None


# ---- aired_count_by_season：每季已播集数计算（过滤 TMDB 脏数据季的依据）----


def test_aired_count_by_season_returning_series():
    """连载剧：早于当前季=总集数，当前季=last_episode，未来季/无首播日=0。"""
    detail = {
        "status": "Returning Series",
        "last_episode_to_air": {"season_number": 2, "episode_number": 3},
        "seasons": [
            {"season_number": 0, "episode_count": 5, "air_date": "2020-01-01"},  # 特典季，排除
            {"season_number": 1, "episode_count": 10, "air_date": "2020-01-01"},  # 早于当前季
            {"season_number": 2, "episode_count": 10, "air_date": "2021-01-01"},  # 当前季
            {"season_number": 3, "episode_count": 8, "air_date": "2099-01-01"},  # 未来季
            {"season_number": 4, "episode_count": 8},  # 无首播日
        ],
    }
    assert aired_count_by_season(detail) == {1: 10, 2: 3, 3: 0, 4: 0}


def test_aired_count_by_season_completed():
    """已完结剧：已开播的季视为全部播出（=总集数）。"""
    detail = {
        "status": "Ended",
        "seasons": [
            {"season_number": 1, "episode_count": 12, "air_date": "2018-01-01"},
            {"season_number": 2, "episode_count": 10, "air_date": "2019-01-01"},
        ],
    }
    assert aired_count_by_season(detail) == {1: 12, 2: 10}


async def test_save_seasons_writes_aired_count_zero_for_unaired(db_session):
    """未开播的季（air_date 在未来）应落库 aired_count=0。"""
    detail = {
        "status": "Returning Series",
        "last_episode_to_air": {"season_number": 1, "episode_number": 5},
        "seasons": [
            {"season_number": 1, "episode_count": 10, "air_date": "2020-01-01"},
            {"season_number": 2, "episode_count": 10, "air_date": "2099-01-01"},  # 未播
        ],
    }
    await save_seasons(db_session, 500, detail)
    rows = (await db_session.execute(select(TmdbSeason).where(TmdbSeason.tmdb_id == 500))).scalars().all()
    by_season = {r.season: r for r in rows}
    assert by_season[1].aired_count == 5  # 当前季 = last_episode
    assert by_season[2].aired_count == 0  # 未播季


async def test_get_seasons_map_skips_unaired_season(db_session, monkeypatch):
    """无已播集数的季不应出现在季集结构中（MP 不会对其建订阅）。"""
    db_session.add(TmdbSeason(tmdb_id=600, season=1, episode_count=10, aired_count=10))
    db_session.add(TmdbSeason(tmdb_id=600, season=2, episode_count=8, aired_count=0))  # 未播，应过滤
    await db_session.commit()

    async def fake_update(self, db, tmdb_id):
        raise AssertionError("已播季 + 新鲜未播季不应触发 TMDB 刷新")

    monkeypatch.setattr(TMDBService, "update_cache_for_tv", fake_update)
    svc = _make_service()
    result = await svc.get_seasons_map(db_session, 600)
    assert result == {1: list(range(1, 11))}  # 仅第 1 季，未播的第 2 季被过滤


async def test_get_seasons_map_caps_range_at_aired(db_session, monkeypatch):
    """连载季集数范围应收敛到已播集数，避免 MP 追未播集。"""
    # 第 1 季计划 10 集但只播了 3 集
    db_session.add(TmdbSeason(tmdb_id=700, season=1, episode_count=10, aired_count=3))
    await db_session.commit()

    async def fake_update(self, db, tmdb_id):
        raise AssertionError("新鲜缓存不应触发 TMDB 刷新")

    monkeypatch.setattr(TMDBService, "update_cache_for_tv", fake_update)
    svc = _make_service()
    result = await svc.get_seasons_map(db_session, 700)
    assert result == {1: [1, 2, 3]}  # 以 aired_count=3 为准，而非 episode_count=10


async def test_get_seasons_map_ttl_no_refresh_within_day(db_session, monkeypatch):
    """未播季识别结果在 1 天 TTL 内应复用缓存，不重查 TMDB。"""
    fresh = datetime.now(UTC) - timedelta(hours=1)  # 1 小时前评估过
    db_session.add(TmdbSeason(tmdb_id=800, season=1, episode_count=8, aired_count=0, updated_at=fresh))
    await db_session.commit()

    called = {"hit": False}

    async def fake_update(self, db, tmdb_id):
        called["hit"] = True
        return None

    monkeypatch.setattr(TMDBService, "update_cache_for_tv", fake_update)
    svc = _make_service()
    result = await svc.get_seasons_map(db_session, 800)
    assert result == {}  # 未播季被过滤
    assert called["hit"] is False  # TTL 内不重查


async def test_get_seasons_map_ttl_refresh_after_day(db_session, monkeypatch):
    """未播季识别结果超过 1 天 TTL 应重新拉 TMDB 复核（届时可能已开播）。"""
    stale = datetime.now(UTC) - timedelta(days=2)  # 2 天前评估的未播季
    db_session.add(TmdbSeason(tmdb_id=900, season=1, episode_count=8, aired_count=0, updated_at=stale))
    await db_session.commit()

    called = {"hit": False}

    async def fake_update(self, db, tmdb_id):
        called["hit"] = True
        # 模拟 TMDB 复核后该季已开播 5 集
        row = await db.get(TmdbSeason, (tmdb_id, 1))
        row.aired_count = 5
        await db.commit()
        return {"tmdb_total_eps": 8}

    monkeypatch.setattr(TMDBService, "update_cache_for_tv", fake_update)
    svc = _make_service()
    result = await svc.get_seasons_map(db_session, 900)
    assert called["hit"] is True  # 过 TTL → 触发复核
    assert result == {1: [1, 2, 3, 4, 5]}  # 复核后该季已播，纳入结构


async def test_get_season_completion(db_session):
    """完结判定：已播>=总集数（且总集数>0）为完结；未播满或脏数据为未完结。"""
    db_session.add(TmdbSeason(tmdb_id=1000, season=1, episode_count=10, aired_count=10))  # 完结
    db_session.add(TmdbSeason(tmdb_id=1000, season=2, episode_count=10, aired_count=3))  # 连载中
    db_session.add(TmdbSeason(tmdb_id=1000, season=3, episode_count=0, aired_count=0))  # 脏数据
    await db_session.commit()

    svc = _make_service()
    result = await svc.get_season_completion(db_session, 1000)
    assert result == {1: True, 2: False, 3: False}
