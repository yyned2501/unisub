"""NextFind 双向同步 — NF → 本地方向阶段（Phase 0 / 1 / 1.5）。

清理 NF 异常订阅、把 NF 状态回写本地、处理拉黑订阅。
均为模块级函数（无共享状态），由 NfSyncEngine 按顺序编排调用。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.core.logger import init_logger
from app.models.subscription import Subscription
from app.schemas.subscription import SubscriptionSyncResult
from app.services.nextfind import NextFindService
from app.services.nf_sync.phases.common import (
    _NF_CONCURRENCY,
    _is_active_status,
    _is_cancelled_status,
    _nf_status,
    _parse_year,
)

logger = init_logger()


async def phase0_clean_abnormal(
    nf: NextFindService,
    nf_subs: list[dict],
    results: list[SubscriptionSyncResult],
) -> None:
    """Phase 0 — 清理 NF 中元数据异常的活跃订阅（无标题/无封面）。"""
    abnormal_items: list[tuple[int, str, str, dict]] = []  # (tid, title, media_type, nf_sub)
    for nf_sub in nf_subs:
        tid_raw = nf_sub.get("tmdb_id")
        if not tid_raw:
            continue
        tid = int(tid_raw)
        title = (nf_sub.get("title") or nf_sub.get("name") or "").strip()
        poster = nf_sub.get("poster") or nf_sub.get("poster_path") or ""
        if _is_cancelled_status(nf_sub):
            continue
        if title and poster:
            continue
        abnormal_items.append((tid, title, nf_sub.get("media_type", "tv"), nf_sub))

    if not abnormal_items:
        return

    sem = asyncio.Semaphore(_NF_CONCURRENCY)

    async def _remove_abnormal(item: tuple[int, str, str, dict]):
        tid, title, mtype, _ = item
        async with sem:
            return item, await nf.remove_subscription(tid, media_type=mtype)

    remove_results = await asyncio.gather(*[_remove_abnormal(i) for i in abnormal_items])
    for item, nf_result in remove_results:
        tid, title, mtype, _ = item
        if "error" not in nf_result:
            results.append(
                SubscriptionSyncResult(
                    tmdb_id=tid,
                    title=title or f"tmdb_{tid}",
                    action="cancelled_abnormal",
                    nf_subscribed=False,
                    message=f"NF 异常订阅已取消（缺元数据）: tmdb_id={tid}",
                )
            )
            logger.info("同步清理 — 取消 NF 异常订阅: tmdb_id=%d, type=%s", tid, mtype)
        else:
            logger.warning("同步清理 — 取消 NF 异常订阅失败: tmdb_id=%d, %s", tid, nf_result)


async def phase1_nf_to_local(
    nf: NextFindService,
    nf_by_tmdb: dict[int, list[dict]],
    local_by_tmdb: dict[int, Subscription],
    results: list[SubscriptionSyncResult],
) -> None:
    """Phase 1 — NF → 本地：更新状态、补全元数据、清理 NF 多余订阅。"""
    for tid, entries in nf_by_tmdb.items():
        # 选代表条目：优先 active + 有标题 + 有封面
        def _score(e: dict) -> tuple:
            has_title = bool((e.get("title") or e.get("name") or "").strip())
            has_poster = bool(e.get("poster") or e.get("poster_path") or "")
            return (_is_active_status(e), has_title, has_poster)

        nf_sub = max(entries, key=_score)
        nf_status = _nf_status(nf_sub)

        # 检查该 tmdb_id 是否有任何 active 条目
        has_active = any(_is_active_status(e) for e in entries)

        # NF 全部已取消：本地有记录且未完成则重新订阅
        if not has_active:
            local_sub = local_by_tmdb.get(tid)
            if not local_sub or local_sub.completed or local_sub.blacklisted:
                continue  # 孤儿 / 已完成 / 已拉黑 → 跳过

            # 用 NF 数据预判是否实际已完成，避免"重新订阅 → NF 取消"循环
            nf_total = int(nf_sub.get("total_episodes") or 0)
            nf_local = int(nf_sub.get("local_episodes") or 0)
            nf_in_lib = bool(nf_sub.get("is_in_library"))
            if local_sub.media_type == "movie" and (nf_in_lib or nf_local > 0):
                local_sub.completed = True
                local_sub.updated_at = datetime.now(UTC)
                logger.info("电影已入库（NF），标记完成: %s (tmdb_id=%d)", local_sub.title, tid)
                continue
            if local_sub.media_type == "tv" and nf_total > 0 and nf_local >= nf_total:
                local_sub.completed = True
                local_sub.updated_at = datetime.now(UTC)
                logger.info(
                    "剧集已播完（NF %d/%d），标记完成: %s (tmdb_id=%d)", nf_local, nf_total, local_sub.title, tid
                )
                continue

            # 本地有记录且确实未完成 → 重新订阅到 NF
            nf_result = await nf.add_subscription(tid, media_type=local_sub.media_type, title=local_sub.title)
            if "error" in nf_result:
                logger.warning("双向同步 — 重新订阅到 NF 失败: %s, %s", local_sub.title, nf_result)
                continue
            logger.info("双向同步 — 重新订阅到 NF: %s (tmdb_id=%d)", local_sub.title, tid)
            nf_id = nf_result.get("id") or nf_result.get("sub_id") or ""
            local_sub.nf_sub_id = str(nf_id) if nf_id else None
            nf_sub["sub_status"] = "active"
            nf_status = "active"

        total_eps = nf_sub.get("total_episodes", 0)
        local_eps = nf_sub.get("local_episodes", 0)
        if total_eps and local_eps is not None:
            nf_missing = max(0, int(total_eps) - int(local_eps))
        else:
            nf_missing = nf_sub.get("missing_eps") or nf_sub.get("fillable_episodes_count", 0)
        nf_missing = int(nf_missing) if nf_missing else 0

        local_sub = local_by_tmdb.get(tid)

        if local_sub:
            _apply_nf_state_to_local(nf, local_sub, nf_sub, nf_status, nf_missing)
            results.append(
                SubscriptionSyncResult(
                    tmdb_id=tid,
                    title=local_sub.title,
                    action="updated",
                    nf_status=local_sub.nf_status,
                    nf_missing_eps=nf_missing,
                    nf_subscribed=True,
                    needs_mp_search=nf_missing > 0,
                    message=f"已同步: {local_sub.title}, 缺集 {nf_missing}",
                )
            )
        else:
            await _cancel_orphan_nf_entries(nf, tid, entries, nf_sub, results)


def _apply_nf_state_to_local(
    nf: NextFindService,
    local_sub: Subscription,
    nf_sub: dict,
    nf_status: str | None,
    nf_missing: int,
) -> None:
    """把 NF 代表条目的状态回写到本地订阅记录。

    Args:
        nf: NextFind 服务实例（用于补全相对海报路径）
        local_sub: 本地订阅记录
        nf_sub: NF 代表条目
        nf_status: NF 订阅状态
        nf_missing: 缺集数
    """
    local_sub.nf_subscribed = True
    local_sub.nf_status = str(nf_status) if nf_status else None
    local_sub.nf_missing_eps = nf_missing
    # 电影：以 NF is_in_library 为准双向同步完成状态
    if local_sub.media_type == "movie":
        in_library = bool(nf_sub.get("is_in_library")) or int(nf_sub.get("local_episodes") or 0) > 0
        if in_library and not local_sub.completed:
            local_sub.completed = True
            logger.info("电影已入库，标记完成: %s (tmdb_id=%d)", local_sub.title, local_sub.tmdb_id)
        elif not in_library and local_sub.completed:
            local_sub.completed = False
            logger.info("电影不在本地库，取消完成标记: %s (tmdb_id=%d)", local_sub.title, local_sub.tmdb_id)
    if not local_sub.year:
        local_sub.year = _parse_year(nf_sub.get("year"))
    if not local_sub.poster_url:
        poster = nf_sub.get("poster") or nf_sub.get("poster_url") or nf_sub.get("poster_path")
        if poster:
            if poster.startswith("/"):
                poster = f"{nf.base_url}{poster}"
            local_sub.poster_url = poster
    local_sub.updated_at = datetime.now(UTC)


async def _cancel_orphan_nf_entries(
    nf: NextFindService,
    tid: int,
    entries: list[dict],
    nf_sub: dict,
    results: list[SubscriptionSyncResult],
) -> None:
    """本地无记录时，从 NF 取消该 tmdb_id 的所有未取消条目。"""
    title = nf_sub.get("title") or nf_sub.get("name") or f"tmdb_{tid}"
    for entry in entries:
        if _is_cancelled_status(entry):
            continue  # 已取消的不用再取消
        nf_result = await nf.remove_subscription(tid, media_type=entry.get("media_type", "tv"))
        if "error" not in nf_result:
            logger.info(f"双向同步 — 从 NF 取消多余订阅: {title} (tmdb_id={tid}, type={entry.get('media_type')})")
    results.append(
        SubscriptionSyncResult(
            tmdb_id=tid,
            title=title,
            action="cancelled_from_nf",
            nf_subscribed=False,
            message=f"NF 多余订阅已取消: {title}",
        )
    )


async def phase1_5_blacklist(
    nf: NextFindService,
    local_all: list[Subscription],
    nf_by_tmdb: dict[int, list[dict]],
    results: list[SubscriptionSyncResult],
) -> None:
    """Phase 1.5 — 拉黑的订阅从 NF 取消。"""
    for local_sub in local_all:
        if not local_sub.blacklisted:
            continue
        entries = nf_by_tmdb.get(local_sub.tmdb_id, [])
        has_active = any(_is_active_status(e) for e in entries)
        if not has_active:
            # NF 端已无活跃条目，仅更新本地标记
            if local_sub.nf_subscribed:
                local_sub.nf_subscribed = False
                local_sub.updated_at = datetime.now(UTC)
            continue
        # NF 端仍有活跃条目 → 调用取消
        nf_result = await nf.remove_subscription(local_sub.tmdb_id, media_type=local_sub.media_type)
        if "error" not in nf_result:
            local_sub.nf_subscribed = False
            local_sub.updated_at = datetime.now(UTC)
            results.append(
                SubscriptionSyncResult(
                    tmdb_id=local_sub.tmdb_id,
                    title=local_sub.title,
                    action="cancelled_blacklisted",
                    nf_subscribed=False,
                    message=f"拉黑取消: {local_sub.title}",
                )
            )
            logger.info("同步拉黑 — 从 NF 取消: %s (tmdb_id=%d)", local_sub.title, local_sub.tmdb_id)
        else:
            logger.warning("同步拉黑 — 从 NF 取消失败: %s, %s", local_sub.title, nf_result)
