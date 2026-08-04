"""NextFind 双向同步 — 完成判定阶段（Phase 3 / 4 / 5）。

基于 NF 状态与本地 Emby/TMDB 缓存判定电影/剧集是否入库完成，
并记录 NF 中不再需要的 cancelled 条目。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import init_logger
from app.models.emby_cache import EmbyCache
from app.models.subscription import Subscription
from app.models.tmdb_cache import TmdbCache
from app.services.nf_sync_phases.common import _is_cancelled_status, _nf_status

logger = init_logger()


def phase3_movie_completed(
    nf_by_tmdb: dict[int, list[dict]],
    local_by_tmdb: dict[int, Subscription],
) -> None:
    """Phase 3 — 更新电影完成状态（仅电影；TV 由 Phase 4 基于 TMDB 数据判断）。"""
    for tid, entries in nf_by_tmdb.items():
        local_sub = local_by_tmdb.get(tid)
        if not local_sub or local_sub.media_type != "movie":
            continue
        for nf_sub in entries:
            if _nf_status(nf_sub) in ("completed", "finished"):
                local_sub.completed = True
                local_sub.updated_at = datetime.now(UTC)
                break


async def phase4_tv_completed(db: AsyncSession, local_all: list[Subscription]) -> None:
    """Phase 4 — 基于本地 Emby/TMDB 缓存判断剧集入库完成。"""
    unfinished_tids = [s.tmdb_id for s in local_all if not s.completed and s.media_type == "tv"]
    if not unfinished_tids:
        return

    emby_rows = (await db.execute(select(EmbyCache).where(EmbyCache.tmdb_id.in_(unfinished_tids)))).scalars().all()
    emby_map = {e.tmdb_id: e for e in emby_rows}
    tmdb_rows = (await db.execute(select(TmdbCache).where(TmdbCache.tmdb_id.in_(unfinished_tids)))).scalars().all()
    tmdb_map = {t.tmdb_id: t for t in tmdb_rows}

    for sub in local_all:
        if sub.completed or sub.media_type != "tv":
            continue
        ec = emby_map.get(sub.tmdb_id)
        if not ec or not ec.emby_episode_count:
            continue

        tc = tmdb_map.get(sub.tmdb_id)
        if not tc:
            continue
        if tc.tmdb_aired_eps:
            if ec.emby_episode_count >= tc.tmdb_aired_eps and not sub.aired_complete:
                sub.aired_complete = True
                sub.updated_at = datetime.now(UTC)
                logger.info(
                    "在播剧已播出集数全部入库: %s (emby=%d, aired=%d)",
                    sub.title,
                    ec.emby_episode_count,
                    tc.tmdb_aired_eps,
                )
        elif tc.tmdb_total_eps:
            if ec.emby_episode_count >= tc.tmdb_total_eps:
                sub.completed = True
                sub.updated_at = datetime.now(UTC)
                logger.info(
                    "完结剧已全部入库: %s (emby=%d, total=%d)",
                    sub.title,
                    ec.emby_episode_count,
                    tc.tmdb_total_eps,
                )


def phase5_log_cancelled(
    nf_by_tmdb: dict[int, list[dict]],
    local_by_tmdb: dict[int, Subscription],
) -> None:
    """Phase 5 — 记录 NF 中不再需要的 cancelled 条目（仅日志，不重复调用取消 API）。"""
    for tid, entries in nf_by_tmdb.items():
        local_sub = local_by_tmdb.get(tid)
        for nf_sub in entries:
            if not _is_cancelled_status(nf_sub):
                continue
            if local_sub and not local_sub.completed and not local_sub.blacklisted:
                continue  # 未完成且未拉黑，Phase 1 会重新订阅
            reason = "本地已完成" if local_sub and local_sub.completed else ("已拉黑" if local_sub else "本地无记录")
            logger.debug("NF 已取消条目（跳过）: tmdb_id=%d, type=%s (%s)", tid, nf_sub.get("media_type"), reason)
