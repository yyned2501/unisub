"""TMDB 季集缓存 — tmdb_cache / tmdb_season 的写库与季结构读取。

从 tmdb.py 拆出：update_cache_for_tv 查详情落库、save_seasons 按季写库、
get_seasons_map / get_season_completion 读本地季结构（未播季带 TTL 复核）。
函数均接收 TMDBService 实例复用其请求能力。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import init_logger
from app.models.tmdb_cache import TmdbCache
from app.models.tmdb_season import TmdbSeason
from app.services.tmdb_detail import aired_count_by_season, aired_from_detail, next_air_date_from_detail

if TYPE_CHECKING:
    from app.services.tmdb import TMDBService

logger = init_logger()

# 未播季重新识别间隔：一旦识别出某季无已播集数并过滤，此间隔内不再查 TMDB 复核，
# 过期后才重新识别（届时该季可能已开播）。过滤掉的季 1 天内直接复用缓存跳过。
SEASON_CACHE_TTL = timedelta(days=1)


async def update_cache_for_tv(service: TMDBService, db: AsyncSession, tmdb_id: int) -> dict | None:
    """查询 TV 剧集的 TMDB 详情并写入本地缓存（tmdb_cache）。

    任何调用方（自动订阅、同步等）调此函数，查到的数据自动落库，
    后续二次使用不再需要重复调 TMDB API。

    Args:
        service: TMDB 服务实例
        db: 数据库会话
        tmdb_id: TMDB ID

    Returns:
        缓存数据字典，或 None（查询失败/非 TV）
    """
    detail = await service.get_tv_detail(tmdb_id)
    if not detail or "error" in detail:
        return None

    # 复用同一份 detail 纯计算，避免对 /tv/{id} 重复发请求
    aired = aired_from_detail(detail)
    next_date = next_air_date_from_detail(detail)
    poster_path = detail.get("poster_path")
    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

    data = {
        "tmdb_total_eps": detail.get("number_of_episodes"),
        "tmdb_aired_eps": aired,
        "tmdb_next_air_date": next_date,
        "poster_url": poster_url,
        "tmdb_poster_path": poster_path,
    }

    tc = await db.get(TmdbCache, tmdb_id)
    if tc:
        tc.tmdb_total_eps = data["tmdb_total_eps"]
        tc.tmdb_aired_eps = data["tmdb_aired_eps"]
        tc.tmdb_next_air_date = data["tmdb_next_air_date"]
        if poster_path:
            tc.tmdb_poster_path = poster_path
        if poster_url:
            tc.poster_url = poster_url
    else:
        db.add(TmdbCache(tmdb_id=tmdb_id, **data))

    # 顺手写入按季集数结构（seasons），供 MP 订阅计算缺集季复用，
    # 避免订阅同步重复访问外部接口。detail 已在手，零额外请求。
    await save_seasons(db, tmdb_id, detail)

    try:
        await db.flush()
    except Exception:
        logger.debug("TMDB 缓存写入失败: tmdb_id=%d", tmdb_id, exc_info=True)
        return None

    return data


async def save_seasons(db: AsyncSession, tmdb_id: int, detail: dict) -> None:
    """把剧集详情的 seasons 按季写入 tmdb_season 表（不 commit，由调用方统一提交）。

    跳过 season_number=0 的特典季。已存在的季更新 episode_count/air_date，
    不存在的新增。

    Args:
        db: 数据库会话
        tmdb_id: TMDB ID
        detail: /tv/{id} 返回的详情字典（含 seasons 列表）
    """
    # 先算每季已播集数（过滤未播季的依据），与季数据一并落库
    aired_map = aired_count_by_season(detail)
    seasons = detail.get("seasons") or []
    for s in seasons:
        sn = s.get("season_number")
        if sn is None or sn == 0:
            continue  # 跳过特典季
        episode_count = s.get("episode_count") or 0
        air_date = s.get("air_date")
        aired_count = aired_map.get(sn, 0)
        # 复合主键 (tmdb_id, season)，用 get 精确取
        existing = await db.get(TmdbSeason, (tmdb_id, sn))
        if existing:
            existing.episode_count = episode_count
            existing.aired_count = aired_count
            existing.air_date = air_date
        else:
            db.add(
                TmdbSeason(
                    tmdb_id=tmdb_id,
                    season=sn,
                    episode_count=episode_count,
                    aired_count=aired_count,
                    air_date=air_date,
                )
            )


async def get_seasons_map(service: TMDBService, db: AsyncSession, tmdb_id: int) -> dict[int, list[int]] | None:
    """获取剧集的季集结构（{季号: [集号列表]}），优先本地缓存，缺失时调 TMDB 补。

    MP notexists 依据此结构逐季比对算缺集。本地 tmdb_season 无数据时，
    调 update_cache_for_tv 查询 TMDB 并落库（一次请求同时刷新整剧缓存与季数据）。

    过滤 TMDB 脏数据：只纳入有已播集数（aired_count>0）的季，集数范围以已播集数
    为准（[1..aired_count]），未开播的季不出现在结构中 → MP 不会对其建订阅。
    未播季的识别结果带 1 天 TTL：距上次评估超过 SEASON_CACHE_TTL 才重新拉 TMDB
    复核，1 天内直接复用缓存跳过，避免每轮同步都重查未播季。

    注意：补缓存经 ``service.update_cache_for_tv`` 实例方法调用，
    保证对类方法的 monkeypatch（测试桩）生效。

    Args:
        service: TMDB 服务实例
        db: 数据库会话
        tmdb_id: TMDB ID

    Returns:
        ``{季号: [集号列表]}``（仅含已播季）；查不到任何季数据时返回 None。
    """
    rows = (await db.execute(select(TmdbSeason).where(TmdbSeason.tmdb_id == tmdb_id))).scalars().all()
    if not rows:
        # 本地无缓存 → 调 TMDB 查询并写入（update_cache_for_tv 内部会 save_seasons）
        await service.update_cache_for_tv(db, tmdb_id)
        rows = (await db.execute(select(TmdbSeason).where(TmdbSeason.tmdb_id == tmdb_id))).scalars().all()

    # 有未播季且其识别结果已过 TTL → 重新拉 TMDB 复核（该季可能已开播）
    if rows and unaired_needs_refresh(service, rows):
        await service.update_cache_for_tv(db, tmdb_id)
        rows = (await db.execute(select(TmdbSeason).where(TmdbSeason.tmdb_id == tmdb_id))).scalars().all()

    if not rows:
        return None

    # 只纳入已播季，集数范围以已播集数为准
    return {row.season: list(range(1, (row.aired_count or 0) + 1)) for row in rows if (row.aired_count or 0) > 0}


async def get_season_completion(db: AsyncSession, tmdb_id: int) -> dict[int, bool]:
    """返回每季是否已完结 ``{季号: 是否完结}``，依据本地 tmdb_season 缓存。

    已播集数达到总集数（aired_count >= episode_count 且总集数>0）视为该季完结。
    供 MP 镜像同步判断：已订阅的季即便暂不缺集，只要未完结（后续还有集要播）
    就保留订阅。纯本地读取，不发外部请求。

    Args:
        db: 数据库会话
        tmdb_id: TMDB ID

    Returns:
        ``{季号: 是否完结}``；无缓存数据的季不包含在内（调用方按未完结保守处理）。
    """
    rows = (await db.execute(select(TmdbSeason).where(TmdbSeason.tmdb_id == tmdb_id))).scalars().all()
    return {
        row.season: (row.episode_count or 0) > 0 and (row.aired_count or 0) >= (row.episode_count or 0) for row in rows
    }


def unaired_needs_refresh(service: TMDBService, rows: list) -> bool:
    """判断是否需要为未播季重新拉 TMDB 复核。

    仅当存在 aired_count=0 的季、且其上次评估（updated_at）距今超过
    SEASON_CACHE_TTL 时才刷新；否则 1 天内复用缓存，不重查未播季。

    Args:
        service: TMDB 服务实例（无 api_key 时不刷新）
        rows: tmdb_season 行列表

    Returns:
        需要刷新返回 True
    """
    if not service.api_key:
        return False
    now = datetime.now(UTC)
    for row in rows:
        if (row.aired_count or 0) != 0:
            continue  # 已播季不在此处触发刷新
        updated = row.updated_at
        if updated is None:
            return True
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=UTC)  # sqlite 可能返回 naive datetime
        if now - updated > SEASON_CACHE_TTL:
            return True
    return False
