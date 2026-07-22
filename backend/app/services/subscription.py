"""订阅数据库操作封装 — 订阅列表查询与缓存关联。

将 routers/subscriptions.py 中的数据库查询逻辑封装到此处，
遵循 routers → services → models 的调用链。
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.emby_cache import EmbyCache
from app.models.subscription import Subscription
from app.models.tmdb_cache import TmdbCache
from app.services.tmdb import TMDBService

_TMDB_SEMAPHORE = asyncio.Semaphore(5)


async def list_subscriptions_with_cache(
    db: AsyncSession,
    nf_base_url: str | None = None,
) -> list[Subscription]:
    """获取所有订阅列表，关联 emby_cache 中的 TMDB 缓存数据。

    先返回 emby_cache 的缓存数据，然后后台异步更新 TMDB 已播出信息。

    Args:
        db: 数据库会话
        nf_base_url: NextFind 基础 URL，用于补全相对路径海报

    Returns:
        订阅列表（含缓存增强的 adjusted_missing_eps / tmdb_aired_eps）
    """
    result = await db.execute(select(Subscription).order_by(Subscription.created_at.desc()))
    subs = result.scalars().all()

    # 补全相对路径的 poster_url
    if nf_base_url:
        nf_base_url = nf_base_url.rstrip("/")
        for sub in subs:
            if sub.poster_url and sub.poster_url.startswith("/"):
                sub.poster_url = f"{nf_base_url}{sub.poster_url}"

    # 从 tmdb_cache 读取已缓存的 TMDB 数据（秒出）
    tmdb_ids = [s.tmdb_id for s in subs if s.media_type == "tv"]
    cache_map: dict[int, TmdbCache] = {}
    emby_cache_map: dict[int, EmbyCache] = {}
    if tmdb_ids:
        cache_result = await db.execute(select(TmdbCache).where(TmdbCache.tmdb_id.in_(tmdb_ids)))
        cache_map = {c.tmdb_id: c for c in cache_result.scalars().all()}
        # 同时读取 emby_cache 获取当前入库数
        ec_result = await db.execute(select(EmbyCache).where(EmbyCache.tmdb_id.in_(tmdb_ids)))
        emby_cache_map = {e.tmdb_id: e for e in ec_result.scalars().all()}
        for sub in subs:
            # 补全缺失的 poster_url（tmdb_cache → emby_cache）
            if not sub.poster_url:
                cached = cache_map.get(sub.tmdb_id)
                if cached and cached.poster_url:
                    sub.poster_url = cached.poster_url
            # 补全 emby 入库数
            ec = emby_cache_map.get(sub.tmdb_id)
            if ec:
                sub.emby_episode_count = ec.emby_episode_count
            # 补全 TMDB 总集数
            tc = cache_map.get(sub.tmdb_id)
            if tc:
                sub.tmdb_total_eps = tc.tmdb_total_eps

    # 从 emby_cache 补全仍缺失的 poster_url
    still_missing = [s.tmdb_id for s in subs if not s.poster_url]
    if still_missing:
        ec_result = await db.execute(select(EmbyCache).where(EmbyCache.tmdb_id.in_(still_missing)))
        for ec in ec_result.scalars().all():
            for sub in subs:
                if sub.tmdb_id == ec.tmdb_id and not sub.poster_url:
                    # emby_cache 没有 poster_url 字段，但可通过 image_url 获取
                    if ec.emby_image_url:
                        sub.poster_url = ec.emby_image_url
                    break

    for sub in subs:
        if sub.media_type != "tv" or sub.nf_missing_eps <= 0:
            continue
        cached = cache_map.get(sub.tmdb_id)
        if cached:
            sub.tmdb_aired_eps = cached.tmdb_aired_eps
            if cached.tmdb_total_eps and cached.tmdb_total_eps > 0:
                in_library = cached.tmdb_total_eps - sub.nf_missing_eps
                aired = cached.tmdb_aired_eps or cached.tmdb_total_eps
                sub.adjusted_missing_eps = max(0, aired - in_library)

    return subs


async def _update_tmdb_cache_for_sub(scan_db, sub, tmdb_service):
    """为单个订阅更新 TMDB 缓存数据（含 poster_url）。"""
    try:
        aired = await tmdb_service.get_aired_episode_count(sub.tmdb_id)
        if aired is None:
            return
        detail = await tmdb_service.get_tv_detail(sub.tmdb_id)
        total = detail.get("number_of_episodes", 0) if detail and "error" not in detail else 0
        poster_path = detail.get("poster_path") if detail and "error" not in detail else None
    except Exception:
        return

    tc = await scan_db.get(TmdbCache, sub.tmdb_id)
    if tc:
        tc.tmdb_aired_eps = aired
        if total:
            tc.tmdb_total_eps = total
        if poster_path and not tc.poster_url:
            tc.poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
    else:
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
        tc = TmdbCache(
            tmdb_id=sub.tmdb_id,
            tmdb_aired_eps=aired,
            tmdb_total_eps=total or None,
            poster_url=poster_url,
        )
        scan_db.add(tc)
    await scan_db.commit()


async def background_update_tmdb_cache(
    tmdb_service: TMDBService | None,
    tv_subs: list[Subscription],
):
    """后台异步更新 TMDB 数据到 tmdb_cache（含 poster_url）。

    Args:
        tmdb_service: TMDB 服务实例
        tv_subs: 需要更新的剧集订阅列表
    """
    if not tmdb_service or not tv_subs:
        return

    from app.core.database import async_session

    async with _TMDB_SEMAPHORE:
        for sub in tv_subs:
            async with async_session() as scan_db:
                await _update_tmdb_cache_for_sub(scan_db, sub, tmdb_service)
                await asyncio.sleep(0.5)
