"""MoviePilot 镜像的缺集季检测。

从 mp_sync.py 拆出的纯查询/计算函数：缺集季优先用本地按季缓存
（tmdb_season 已播集数 - emby_season_cache 库内集数）计算，
同步缺口才回退调 MP notexists 兜底。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import init_logger
from app.models.emby_cache import EmbyCache
from app.models.emby_season_cache import EmbySeasonCache
from app.models.subscription import Subscription

if TYPE_CHECKING:
    from app.services.mp_sync import MpSyncEngine

logger = init_logger()


async def query_missing_seasons(engine: MpSyncEngine, db: AsyncSession, sub: Subscription) -> list[dict] | None:
    """查询剧集缺集季 — 优先本地计算，同步缺口才用 MP notexists 兜底。

    缺集 = 已播集数（tmdb_season）- 库内集数（emby_season_cache），纯本地 DB 计算，
    不再每轮实时调 MP notexists（其频繁打 Emby、慢且易 502）。判定路径：
        - 本地有按季库数据 → 本地算缺集
        - 本地无按季数据且剧不在 Emby 库 → 所有已播集都缺（本地判定，不调 notexists）
        - 本地无按季数据但剧在库（同步缺口）→ 回退调一次 notexists 兜底

    Returns:
        缺集季列表（``[{"season","episodes","total_episode"}, ...]``）；
        失败/无季集结构返回 None，无缺集返回 []。
    """
    seasons_map: dict[int, list[int]] | None = None
    if engine.tmdb:
        try:
            seasons_map = await engine.tmdb.get_seasons_map(db, sub.tmdb_id)
        except Exception as e:
            logger.warning("获取季集结构失败: %s (tmdb_id=%d), %s", sub.title, sub.tmdb_id, e)

    if not seasons_map:
        logger.debug("无季集结构，跳过 MP 缺集查询: %s (tmdb_id=%d)", sub.title, sub.tmdb_id)
        return None

    emby_counts = await emby_season_counts(db, sub.tmdb_id)
    if emby_counts:
        return diff_missing(seasons_map, emby_counts)

    if not await show_in_emby(db, sub.tmdb_id):
        # 剧不在 Emby 库 → 不镜像（只补已在库剧的缺集，不整部下载），返回"无缺集"
        logger.debug("剧不在 Emby 库，跳过 MP 镜像: %s (tmdb_id=%d)", sub.title, sub.tmdb_id)
        return []

    # 剧在库但无按季缓存（同步缺口）→ notexists 兜底一次
    logger.debug("本地无按季库缓存，notexists 兜底: %s (tmdb_id=%d)", sub.title, sub.tmdb_id)
    return await query_missing_via_mp(engine, sub, seasons_map)


def diff_missing(seasons_map: dict[int, list[int]], emby_counts: dict[int, int]) -> list[dict]:
    """本地计算缺集季，返回与 MP notexists 兼容的结构。

    假设库内集按序补齐（1..have），缺集为 have+1..aired。

    Args:
        seasons_map: ``{季号: [已播集号列表]}``（来自 tmdb_season）
        emby_counts: ``{季号: 库内集数}``（来自 emby_season_cache）

    Returns:
        缺集季列表（仅含 已播 > 库内 的季）
    """
    missing: list[dict] = []
    for sn, eps in seasons_map.items():
        aired = len(eps)
        have = emby_counts.get(sn, 0)
        if aired > have:
            missing.append({"season": sn, "episodes": list(range(have + 1, aired + 1)), "total_episode": aired})
    return missing


async def emby_season_counts(db: AsyncSession, tmdb_id: int) -> dict[int, int]:
    """读取本地 emby_season_cache 的按季库内集数 ``{季号: 集数}``。"""
    rows = (await db.execute(select(EmbySeasonCache).where(EmbySeasonCache.tmdb_id == tmdb_id))).scalars().all()
    return {row.season: (row.episode_count or 0) for row in rows}


async def show_in_emby(db: AsyncSession, tmdb_id: int) -> bool:
    """判断剧是否在 Emby 库中（emby_cache 有该 tmdb_id 记录）。"""
    row = (await db.execute(select(EmbyCache.tmdb_id).where(EmbyCache.tmdb_id == tmdb_id))).first()
    return row is not None


async def query_missing_via_mp(
    engine: MpSyncEngine, sub: Subscription, seasons_map: dict[int, list[int]]
) -> list[dict] | None:
    """兜底：调 MP notexists 查缺集（仅本地按季缓存缺口时使用）。"""
    result = await engine.mp.get_missing_seasons(
        sub.tmdb_id, sub.media_type, sub.title, year=sub.year, seasons=seasons_map
    )
    if isinstance(result, dict) and "error" in result:
        logger.warning("MP 缺集查询失败（跳过镜像）: %s, %s", sub.title, result)
        return None
    if not isinstance(result, list):
        return None
    return result
