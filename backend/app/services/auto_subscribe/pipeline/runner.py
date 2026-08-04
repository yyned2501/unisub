"""自动订阅 — 流水线编排：Fetch → Filter → Search → Subscribe。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import init_logger

# 导入各来源模块以触发 @register 自注册（不直接使用模块对象）。
from app.services.auto_subscribe import douban, maoyan, mikan  # noqa: F401
from app.services.auto_subscribe.base import get_provider
from app.services.auto_subscribe.models import (
    SOURCE_NAMES,
    STATUS_ALREADY,
    STATUS_ERROR,
    STATUS_EXISTS,
    STATUS_FILTERED,
    STATUS_IN_LIBRARY,
    STATUS_SUBSCRIBED,
    STATUS_UNRECOGNIZED,
    TERMINAL_STATUSES,
    RankMediaItem,
    make_history_key,
)
from app.services.auto_subscribe.pipeline.filters import (
    passes_global_filter,
    passes_source_filter,
    source_options,
    vote_filter_reason,
    year_filter_reason,
)
from app.services.auto_subscribe.pipeline.resolve import resolve_best_match
from app.services.auto_subscribe.pipeline.subscription import finalize_subscription
from app.services.nextfind import NextFindAuthError, NextFindService
from app.services.tmdb import TMDBService

logger = init_logger(__name__)

# 每源并发数
_SEARCH_CONCURRENCY = 5


async def run(
    cfg: dict,
    db: AsyncSession,
    nf_service: NextFindService,
    tmdb_service: TMDBService | None = None,
    handled: dict | None = None,
    nf_cache: dict | None = None,
) -> dict:
    """执行一次自动订阅流水线。

    流程:
        1. 遍历启用的榜单源，并发抓取
        2. 全局过滤 + 每源过滤
        3. 对每个条目搜索 TMDB（优先）或 NextFind
        4. 搜索结果过 filter（评分、年份、类型）
        5. 检查是否已订阅（本地 DB）
        6. 新条目 → 创建订阅
        7. 记录处理历史

    Args:
        cfg: 配置字典
        db: 数据库会话
        nf_service: NextFind 服务实例
        tmdb_service: TMDB 服务实例（可选，优先使用）
        handled: 已处理记录缓存（跨轮去重）
        nf_cache: NextFind 订阅缓存（跨轮复用）

    Returns:
        运行结果 dict: {stats, errors, added, handled}
    """
    cfg = {**cfg}
    cfg["nf_cache"] = nf_cache or {}
    handled = handled or {}

    stats: dict[str, dict[str, int]] = {}
    errors: dict[str, str] = {}
    added: list[dict] = []
    new_handled = dict(handled)

    # 1-2. 并发抓取各榜单源，合并为 (源名, 条目) 列表
    all_items = await _fetch_all_sources(cfg, stats, errors)

    logger.info(f"[自动订阅] 共获取 {len(all_items)} 个条目，开始搜索{' TMDB' if tmdb_service else ' NextFind'}...")

    # 3. 搜索并处理（并发控制 + 鉴权失败快速中止）
    sem = asyncio.Semaphore(_SEARCH_CONCURRENCY)
    db_lock = asyncio.Lock()  # DB 写操作串行化，避免并发 commit 冲突
    abort = asyncio.Event()  # 鉴权失败时置位，其余任务提前退出
    auth_error = ""

    async def _process(src_name: str, item: RankMediaItem):
        nonlocal auth_error
        if abort.is_set():
            return
        async with sem:
            if abort.is_set():
                return
            try:
                return await _search_and_subscribe(
                    cfg,
                    src_name,
                    item,
                    nf_service,
                    tmdb_service,
                    db,
                    db_lock,
                    new_handled,
                    stats,
                    added,
                )
            except NextFindAuthError as exc:
                # 密钥无效/过期：继续跑只会每条都 401，立即中止整轮并明确报因。
                auth_error = str(exc)
                abort.set()
                logger.error(f"[自动订阅] {exc}，已中止本轮")

    tasks = [_process(src_name, item) for src_name, item in all_items]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # 逐条检查 gather 结果：未被 _process 捕获的异常不能静默丢弃，逐条记日志
    for (src_name, item), res in zip(all_items, results):
        if isinstance(res, BaseException):
            logger.error("[自动订阅] 处理条目异常: %s (%s): %s", item.title, src_name, res)

    return {
        "stats": stats,
        "errors": errors,
        "added": added,
        "handled": new_handled,
        "nf_cache": cfg.get("nf_cache", {}),
        "auth_error": auth_error,
    }


async def _fetch_all_sources(cfg: dict, stats: dict, errors: dict) -> list[tuple[str, RankMediaItem]]:
    """并发抓取所有启用的榜单源（通过注册表取 provider），返回 (源名, 条目) 列表。"""
    task_sources: list[str] = []
    fetch_tasks = []
    for src_name in (s for s in SOURCE_NAMES if cfg.get(f"{s}_enabled", False)):
        provider = get_provider(src_name)
        if provider is None:
            logger.warning(f"[自动订阅] 未注册的来源: {src_name}，跳过")
            continue
        task_sources.append(src_name)
        fetch_tasks.append(_fetch_with_stats(src_name, provider, source_options(cfg, src_name), stats, errors))

    results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
    all_items: list[tuple[str, RankMediaItem]] = []
    for src_name, r in zip(task_sources, results):
        if isinstance(r, Exception):
            logger.error(f"[自动订阅] 榜单抓取异常: {r}")
        elif isinstance(r, list):
            all_items.extend((src_name, item) for item in r)
    return all_items


async def _fetch_with_stats(
    src_name: str,
    provider,
    options: dict,
    stats: dict,
    errors: dict,
) -> list[RankMediaItem]:
    """抓取榜单源并记录统计。"""
    try:
        items = await provider.fetch_async(options)
        stats.setdefault(src_name, {})["fetched"] = len(items)
        logger.info(f"[{SOURCE_NAMES.get(src_name, src_name)}] 抓取到 {len(items)} 个条目")
        return items
    except Exception as e:
        logger.error(f"[{src_name}] 抓取失败: {e}")
        errors[src_name] = str(e)
        stats.setdefault(src_name, {})["fetched"] = 0
        return []


async def _search_and_subscribe(
    cfg: dict,
    src_name: str,
    item: RankMediaItem,
    nf_service: NextFindService,
    tmdb_service: TMDBService | None,
    db: AsyncSession,
    db_lock: asyncio.Lock,
    new_handled: dict,
    stats: dict,
    added: list,
) -> None:
    """搜索 TMDB（优先）或 NextFind，并决定是否订阅。"""
    title = item.title
    type_hint = item.type_hint or "all"  # RSS 未提供类别时才搜索全部
    seed = item.unique_seed or title

    # 跨轮去重：历史里该 seed 已是正向终态才跳过（filtered/unrecognized 不跳过，可重评）
    prev = new_handled.get(seed)
    if prev and prev.get("status") in TERMINAL_STATUSES:
        _inc_stat(stats, src_name, STATUS_ALREADY)
        return

    # 全局过滤 + 每源过滤
    passed, reason = passes_global_filter(cfg, item)
    if passed:
        passed, reason = passes_source_filter(cfg, src_name, item)
    if not passed:
        _inc_stat(stats, src_name, STATUS_FILTERED)
        new_handled[seed] = {
            "status": STATUS_FILTERED,
            "title": title,
            "reason": reason,
            "source": src_name,
            "time": _now_str(),
        }
        return

    # 搜索 + 匹配解析（搜索词变体 → 多轮搜索 → fallback 链 → 最佳匹配 → 相似度校验）
    best = await resolve_best_match(item, type_hint, nf_service, tmdb_service)
    if not best:
        _inc_stat(stats, src_name, STATUS_UNRECOGNIZED)
        new_handled[seed] = {"status": STATUS_UNRECOGNIZED, "title": title, "source": src_name, "time": _now_str()}
        return

    tmdb_id = int(best["id"])
    matched_title = (best.get("title") or best.get("name") or title).strip() or title
    media_type = best.get("raw_type", type_hint)
    vote = best.get("_vote_average") or best.get("vote_average") or 0
    year = best.get("year") or item.year
    poster = best.get("poster") or best.get("poster_url") or item.poster

    # 跨源去重：按解析后的 tmdb_id 生成历史键，已是正向终态则跳过
    season = item.season if media_type == "tv" else None
    history_key = make_history_key(tmdb_id, media_type, season)
    prev_key = new_handled.get(history_key)
    if prev_key and prev_key.get("status") in TERMINAL_STATUSES:
        _inc_stat(stats, src_name, STATUS_ALREADY)
        return

    def _mark_terminal(status: str) -> None:
        """正向终态：同时按 seed 与 tmdb 历史键记录，供跨轮 + 跨源去重。"""
        entry = {
            "status": status,
            "tmdb_id": tmdb_id,
            "media_type": media_type,
            "title": matched_title,
            "source": src_name,
            "time": _now_str(),
        }
        new_handled[seed] = entry
        new_handled[history_key] = entry

    # 搜索后过滤：评分（全局 + 每源取较高者）、最小年份（多季剧看最新季）
    reason = vote_filter_reason(cfg, src_name, vote) or await year_filter_reason(
        cfg, src_name, year, media_type, tmdb_id, matched_title, tmdb_service
    )
    if reason:
        _inc_stat(stats, src_name, STATUS_FILTERED)
        new_handled[seed] = {
            "status": STATUS_FILTERED,
            "title": matched_title,
            "reason": reason,
            "tmdb_id": tmdb_id,
            "media_type": media_type,
            "source": src_name,
            "time": _now_str(),
        }
        return

    # 订阅阶段收尾：写 TMDB 缓存 → 已订阅/已在库检查 → 远端创建 + 本地持久化
    status = await finalize_subscription(
        db,
        db_lock,
        nf_service,
        tmdb_service,
        best,
        tmdb_id,
        matched_title,
        media_type,
        poster,
        year,
        src_name,
    )
    _inc_stat(stats, src_name, status)
    if status == STATUS_SUBSCRIBED:
        added.append({"tmdb_id": tmdb_id, "title": matched_title, "source": src_name, "media_type": media_type})
        _mark_terminal(status)
    elif status in (STATUS_EXISTS, STATUS_IN_LIBRARY):
        _mark_terminal(status)
    else:
        new_handled[seed] = {"status": STATUS_ERROR, "title": matched_title, "source": src_name, "time": _now_str()}


def _inc_stat(stats: dict, src_name: str, status: str):
    """递增统计计数器。"""
    s = stats.setdefault(src_name, {})
    s[status] = s.get(status, 0) + 1


def _now_str() -> str:
    """返回当前 UTC 时间 ISO 字符串。"""
    return datetime.now(UTC).isoformat()
