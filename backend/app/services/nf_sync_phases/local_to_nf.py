"""NextFind 双向同步 — 本地 → NF 方向阶段（Phase 2）。

把本地未完成的订阅推送到 NF（并发限流）。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.core.logger import init_logger
from app.models.subscription import Subscription
from app.schemas.subscription import SubscriptionSyncResult
from app.services.nextfind import NextFindService
from app.services.nf_sync_phases.common import _NF_CONCURRENCY, _is_active_status

logger = init_logger()


async def phase2_local_to_nf(
    nf: NextFindService,
    local_all: list[Subscription],
    nf_by_tmdb: dict[int, list[dict]],
    results: list[SubscriptionSyncResult],
) -> None:
    """Phase 2 — 本地 → NF：推送未完成的本地订阅到 NF（并发限流）。"""
    push_candidates: list[Subscription] = []
    for local_sub in local_all:
        if local_sub.completed or local_sub.blacklisted:
            continue
        entries = nf_by_tmdb.get(local_sub.tmdb_id, [])
        has_active = any(_is_active_status(e) for e in entries)
        if has_active:
            continue
        push_candidates.append(local_sub)

    if not push_candidates:
        return

    sem2 = asyncio.Semaphore(_NF_CONCURRENCY)

    async def _push_to_nf(sub: Subscription):
        async with sem2:
            return sub, await nf.add_subscription(sub.tmdb_id, media_type=sub.media_type, title=sub.title)

    push_results = await asyncio.gather(*[_push_to_nf(s) for s in push_candidates])
    for local_sub, nf_result in push_results:
        if "error" not in nf_result:
            local_sub.nf_subscribed = True
            nf_id = nf_result.get("id") or nf_result.get("sub_id") or ""
            local_sub.nf_sub_id = str(nf_id) if nf_id else None
            local_sub.updated_at = datetime.now(UTC)
            results.append(
                SubscriptionSyncResult(
                    tmdb_id=local_sub.tmdb_id,
                    title=local_sub.title,
                    action="pushed_to_nf",
                    nf_subscribed=True,
                    message=f"已推送到 NF: {local_sub.title}",
                )
            )
            logger.info("双向同步 — 推送订阅到 NF: %s (tmdb_id=%d)", local_sub.title, local_sub.tmdb_id)
        else:
            logger.warning("双向同步 — 推送订阅到 NF 失败: %s, %s", local_sub.title, nf_result)
