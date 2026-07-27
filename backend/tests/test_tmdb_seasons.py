"""TMDB 季集缓存测试 — _save_seasons 写库与 get_seasons_map 本地/补缓存逻辑。"""

from sqlalchemy import select

from app.models.tmdb_season import TmdbSeason
from app.services.tmdb import TMDBService


def _make_service() -> TMDBService:
    """构造测试用 TMDB 服务（api_key 占位，测试中 mock 网络调用）。"""
    return TMDBService("fake-key")


async def test_save_seasons_writes_rows_skip_special(db_session):
    """_save_seasons 应按季写库，跳过特典季（season_number=0）。"""
    svc = _make_service()
    detail = {
        "seasons": [
            {"season_number": 0, "episode_count": 5},  # 特典季，应跳过
            {"season_number": 1, "episode_count": 12, "air_date": "2022-10-03"},
            {"season_number": 2, "episode_count": 10, "air_date": "2023-10-01"},
        ]
    }
    await svc._save_seasons(db_session, 209311, detail)

    rows = (await db_session.execute(select(TmdbSeason).where(TmdbSeason.tmdb_id == 209311))).scalars().all()
    seasons = sorted(r.season for r in rows)
    assert seasons == [1, 2]  # 特典季 0 未入库
    by_season = {r.season: r for r in rows}
    assert by_season[1].episode_count == 12
    assert by_season[1].air_date == "2022-10-03"
    assert by_season[2].episode_count == 10


async def test_save_seasons_updates_existing(db_session):
    """已存在的季应更新 episode_count，而非重复插入。"""
    svc = _make_service()
    db_session.add(TmdbSeason(tmdb_id=100, season=1, episode_count=5))
    await db_session.flush()

    await svc._save_seasons(db_session, 100, {"seasons": [{"season_number": 1, "episode_count": 8}]})
    await db_session.flush()

    rows = (await db_session.execute(select(TmdbSeason).where(TmdbSeason.tmdb_id == 100))).scalars().all()
    assert len(rows) == 1
    assert rows[0].episode_count == 8


async def test_get_seasons_map_local_hit(db_session, monkeypatch):
    """本地有缓存时直接返回，不调 TMDB API。"""
    db_session.add(TmdbSeason(tmdb_id=200, season=1, episode_count=3))
    db_session.add(TmdbSeason(tmdb_id=200, season=2, episode_count=2))
    await db_session.commit()

    called = {"hit": False}

    async def fake_update(self, db, tmdb_id):
        called["hit"] = True
        return None

    monkeypatch.setattr(TMDBService, "update_cache_for_tv", fake_update)
    svc = _make_service()
    result = await svc.get_seasons_map(db_session, 200)

    assert result == {1: [1, 2, 3], 2: [1, 2]}
    assert called["hit"] is False  # 本地命中，未调 TMDB


async def test_get_seasons_map_local_miss_triggers_tmdb(db_session, monkeypatch):
    """本地无缓存时应调 update_cache_for_tv 补数据后再返回。"""

    async def fake_update(self, db, tmdb_id):
        # 模拟调 TMDB 后写入季数据
        await self._save_seasons(db, tmdb_id, {"seasons": [{"season_number": 1, "episode_count": 4}]})
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
