"""Emby 缓存 TMDB 数据批量更新 — 从 EmbyService 中拆出的独立模块。

负责批量查询 TMDB 详情并写入 tmdb_cache 表，
支持三种模式：subscribed（仅已订阅）、missing（仅缺失）、all（全量）。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import init_logger
from app.models.emby_cache import EmbyCache
from app.models.tmdb_cache import TmdbCache
from app.services.poster import build_tmdb_poster_url
from app.services.tmdb import TMDBService

logger = init_logger(__name__)


async def update_tmdb_data_batch(
    db: AsyncSession,
    tmdb_service: TMDBService,
    mode: str = "all",
    progress_callback: Callable[[int, int], Awaitable[None]] | None = None,
) -> dict:
    """批量补充 TMDB 数据到 tmdb_cache。

    Args:
        db: 数据库会话
        tmdb_service: TMDB 服务实例
        mode: "subscribed" 仅已订阅 / "missing" 仅缺失 / "all" 全部
        progress_callback: 进度回调 async func(current, total)

    Returns:
        更新统计信息 {"updated": N, "total": M}
    """
    today_str = date.today().isoformat()

    # 获取已订阅 ID（仅 subscribed 模式需要）
    subscribed_ids: set[int] = set()
    if mode == "subscribed":
        from app.models.subscription import Subscription

        sub_stmt = select(Subscription.tmdb_id).where(
            Subscription.media_type == "tv",
            Subscription.nf_subscribed == True,  # noqa: E712
        )
        sub_result = await db.execute(sub_stmt)
        subscribed_ids = {row[0] for row in sub_result.all()}

    # 获取所有有 emby_episode_count 的缓存记录
    stmt = select(EmbyCache).where(
        EmbyCache.emby_episode_count.isnot(None),
        EmbyCache.emby_episode_count > 0,
    )
    emby_cached = (await db.execute(stmt)).scalars().all()

    # 筛选需要刷新的
    to_update = []
    for c in emby_cached:
        if mode == "subscribed" and c.tmdb_id not in subscribed_ids:
            continue
        tc = await db.get(TmdbCache, c.tmdb_id)
        if mode == "missing":
            if tc is not None:
                continue  # 已有则跳过
        else:
            if tc is not None and not (tc.tmdb_next_air_date and tc.tmdb_next_air_date < today_str):
                continue  # 不需要刷新
        to_update.append(c)

    total = len(to_update)
    if total == 0:
        logger.info("TMDB 更新: 无记录需要刷新，跳过")
        return {"updated": 0, "total": 0}

    # 并发参数
    if mode == "subscribed":
        sem_count, batch_size, batch_sleep = None, total, 0
    elif mode == "missing":
        sem_count, batch_size, batch_sleep = 3, 3, 0.3
    else:
        sem_count, batch_size, batch_sleep = 5, 5, 0.5

    sem = asyncio.Semaphore(sem_count) if sem_count else None

    async def _fetch(tid: int) -> tuple[int, dict]:
        if sem:
            async with sem:
                return await _do_fetch(tid)
        return await _do_fetch(tid)

    async def _do_fetch(tid: int) -> tuple[int, dict]:
        try:
            detail = await tmdb_service.get_tv_detail(tid)
            if detail and "error" not in detail:
                aired = tmdb_service.aired_from_detail(detail)
                next_date = tmdb_service.next_air_date_from_detail(detail)
                poster = detail.get("poster_path")
                return tid, {
                    "total_eps": detail.get("number_of_episodes"),
                    "aired_eps": aired,
                    "next_air_date": next_date,
                    "poster_path": poster,
                    "poster_url": build_tmdb_poster_url(poster),
                }
            if detail and "404" in detail.get("error", ""):
                return tid, {"tmdb_404": True}
        except Exception as e:
            logger.warning("TMDB 详情拉取异常 (tmdb_id=%s): %s", tid, e)
        return tid, {}

    async def _upsert(cache: EmbyCache, data: dict) -> bool:
        tc = await db.get(TmdbCache, cache.tmdb_id)
        if data.get("tmdb_404"):
            if tc:
                tc.tmdb_404 = True
            else:
                tc = TmdbCache(tmdb_id=cache.tmdb_id, tmdb_404=True)
                db.add(tc)
            return True
        if tc:
            tc.tmdb_total_eps = data.get("total_eps")
            tc.tmdb_aired_eps = data.get("aired_eps")
            tc.tmdb_next_air_date = data.get("next_air_date")
            tc.tmdb_poster_path = data.get("poster_path")
            tc.poster_url = data.get("poster_url")
        else:
            tc = TmdbCache(
                tmdb_id=cache.tmdb_id,
                tmdb_total_eps=data.get("total_eps"),
                tmdb_aired_eps=data.get("aired_eps"),
                tmdb_next_air_date=data.get("next_air_date"),
                tmdb_poster_path=data.get("poster_path"),
                poster_url=data.get("poster_url"),
            )
            db.add(tc)
        return True

    log_label = {"subscribed": "已订阅", "missing": "缺失补充", "all": "全量"}[mode]
    logger.info("TMDB %s: %d 条记录, 开始扫描...", log_label, total)

    updated = 0
    for i in range(0, total, batch_size):
        batch = to_update[i : i + batch_size]
        tasks = [_fetch(c.tmdb_id) for c in batch]
        results = await asyncio.gather(*tasks)
        tmdb_map = dict(results)

        for cache in batch:
            data = tmdb_map.get(cache.tmdb_id, {})
            if not data:
                continue
            if await _upsert(cache, data):
                updated += 1

        if progress_callback:
            await progress_callback(min(i + batch_size, total), total)

        if mode != "subscribed":
            if (i + batch_size) % (batch_size * 10) == 0 or i + batch_size >= total:
                await db.commit()
                logger.info("TMDB %s 进度: %d/%d, 已更新 %d", log_label, min(i + batch_size, total), total, updated)
            if batch_sleep:
                await asyncio.sleep(batch_sleep)

    await db.commit()
    logger.info("TMDB %s 完成: 更新 %d/%d 条", log_label, updated, total)
    return {"updated": updated, "total": total}
