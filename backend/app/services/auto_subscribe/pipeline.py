"""自动订阅 — 核心编排：Fetch → Filter → Search → Subscribe。"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import init_logger
from app.models.activity_log import ActivityLog
from app.models.subscription import Subscription
from app.services.auto_subscribe import douban, maoyan, mikan
from app.services.auto_subscribe.models import (
    SOURCE_NAMES,
    STATUS_ALREADY,
    STATUS_ERROR,
    STATUS_EXISTS,
    STATUS_FILTERED,
    STATUS_IN_LIBRARY,
    STATUS_SUBSCRIBED,
    STATUS_UNRECOGNIZED,
    RankMediaItem,
)
from app.services.nextfind import NextFindService
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

    # 1. 并发抓取各榜单源
    fetch_tasks = []
    source_map = {"douban": douban, "mikan": mikan, "maoyan": maoyan}
    enabled_sources = [s for s in source_map if cfg.get(f"{s}_enabled", False)]

    for src_name in enabled_sources:
        src_module = source_map[src_name]
        src_opts = _source_options(cfg, src_name)
        fetch_tasks.append(_fetch_with_stats(src_name, src_module, src_opts, stats, errors))

    results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"[自动订阅] 榜单抓取异常: {r}")

    # 2. 合并抓取结果，按源处理
    all_items: list[tuple[str, RankMediaItem]] = []
    for src_name, items in [(s, r) for s, r in zip(enabled_sources, results) if isinstance(r, list)]:
        for item in items:
            all_items.append((src_name, item))

    logger.info(f"[自动订阅] 共获取 {len(all_items)} 个条目，开始搜索{' TMDB' if tmdb_service else ' NextFind'}...")

    # 3. 搜索并处理（串行 + 并发控制）
    sem = asyncio.Semaphore(_SEARCH_CONCURRENCY)
    db_lock = asyncio.Lock()  # DB 写操作串行化，避免并发 commit 冲突

    async def _process(src_name: str, item: RankMediaItem):
        async with sem:
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

    tasks = [_process(src_name, item) for src_name, item in all_items]
    await asyncio.gather(*tasks, return_exceptions=True)

    return {
        "stats": stats,
        "errors": errors,
        "added": added,
        "handled": new_handled,
        "nf_cache": cfg.get("nf_cache", {}),
    }


async def _fetch_with_stats(
    src_name: str,
    src_module,
    options: dict,
    stats: dict,
    errors: dict,
) -> list[RankMediaItem]:
    """抓取榜单源并记录统计。"""
    try:
        items = await src_module.fetch(options)
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

    # 检查历史去重
    seed = item.unique_seed or title
    if seed in new_handled:
        _inc_stat(stats, src_name, STATUS_ALREADY)
        return

    # 全局过滤
    if not _passes_global_filter(cfg, item):
        _inc_stat(stats, src_name, STATUS_FILTERED)
        new_handled[seed] = {"status": STATUS_FILTERED, "time": _now_str()}
        return

    # 每源过滤
    if not _passes_source_filter(cfg, src_name, item):
        _inc_stat(stats, src_name, STATUS_FILTERED)
        new_handled[seed] = {"status": STATUS_FILTERED, "time": _now_str()}
        return

    # 搜索 — 优先用 TMDB 直搜，fallback 到 NextFind
    search_queries = [title]

    # 剧集类标题：剥离 "第十季" / "第三季" 等季节后缀，用基础标题搜索
    season_match = re.search(r"[第]([一二三四五六七八九十百\d]+)[季]", title)
    if season_match:
        raw = season_match.group(1)
        _ = int(raw) if raw.isdigit() else None  # 只用于判断是否匹配到季号
        base_title = title[: season_match.start()].strip()
        if base_title:
            search_queries = [base_title]
    else:
        # 冒号分割副标题："复仇者联盟5：毁灭之日" → "复仇者联盟5"
        colon_parts = re.split(r"[：:]\s*", title, maxsplit=1)
        if len(colon_parts) > 1 and len(colon_parts[0]) >= 2:
            search_queries.append(colon_parts[0].strip())

        # 数字结尾标题先保留完整名称搜索；无候选时才剥离后缀重试。
        numeric_tail = re.search(r"(\d{1,4})$", title)
        if numeric_tail:
            base_title = title[: numeric_tail.start()].strip()
            if len(base_title) >= 2 and base_title not in search_queries:
                search_queries.append(base_title)

    search_results = None
    search_error = None

    async def _search_once(query: str, search_type: str) -> list[dict] | None:
        """按指定类别搜索，优先 TMDB，空结果时回退 NextFind。"""
        nonlocal search_error
        if tmdb_service:
            try:
                tmdb_results = await tmdb_service.search(query, search_type)
                if tmdb_results:
                    return tmdb_results
            except Exception as e:
                search_error = e
                logger.warning(f"[自动订阅] TMDB 搜索异常: {title}: {e}")
        try:
            nf_results = await nf_service.search_tmdb(query, search_type)
            if nf_results:
                if search_error:
                    logger.info(f"[自动订阅] NextFind 搜索兜底成功: {title}")
                return nf_results
        except Exception as e:
            search_error = e
            logger.warning(f"[自动订阅] NF 搜索异常: {title}: {e}")
        return None

    # 指定类别时，先遍历全部查询变体；均无结果时才使用 all 兜底。
    typed_search_types = [type_hint] if type_hint in ("movie", "tv") else ["all"]
    for search_type in typed_search_types:
        for query in search_queries:
            search_results = await _search_once(query, search_type)
            if search_results:
                break
        if search_results:
            break

    if not search_results and type_hint in ("movie", "tv"):
        for query in search_queries:
            search_results = await _search_once(query, "all")
            if search_results:
                break

    if not search_results:
        _inc_stat(stats, src_name, STATUS_UNRECOGNIZED)
        new_handled[seed] = {"status": STATUS_UNRECOGNIZED, "time": _now_str()}
        return

    # 取最佳匹配
    best = _pick_best(search_results, title, type_hint, item.year)
    if not best:
        _inc_stat(stats, src_name, STATUS_UNRECOGNIZED)
        new_handled[seed] = {"status": STATUS_UNRECOGNIZED, "time": _now_str()}
        return

    # 标题相似度校验：防止完全不匹配的条目被错误订阅
    best_title = (best.get("title") or best.get("name") or "").strip()
    if best_title and not _title_similar_enough(title, best_title):
        _inc_stat(stats, src_name, STATUS_UNRECOGNIZED)
        new_handled[seed] = {"status": STATUS_UNRECOGNIZED, "time": _now_str()}
        return

    tmdb_id = int(best["id"])
    matched_title = (best.get("title") or best.get("name") or title).strip() or title
    media_type = best.get("raw_type", type_hint)
    vote = best.get("_vote_average") or best.get("vote_average") or 0
    year = best.get("year") or item.year
    poster = best.get("poster") or best.get("poster_url") or item.poster

    # 评分过滤
    min_vote = cfg.get("min_vote", 0) or 0
    if min_vote > 0 and (vote < min_vote or vote == 0):
        _inc_stat(stats, src_name, STATUS_FILTERED)
        new_handled[seed] = {"status": STATUS_FILTERED, "time": _now_str()}
        return

    # TMDB 搜索无 is_subscribed/is_in_library 字段，从本地 DB 查询
    if not best.get("is_subscribed"):
        existing = await db.execute(select(Subscription).where(Subscription.tmdb_id == tmdb_id))
        if existing.scalar_one_or_none():
            _inc_stat(stats, src_name, STATUS_EXISTS)
            new_handled[seed] = {
                "status": STATUS_EXISTS,
                "tmdb_id": tmdb_id,
                "media_type": media_type,
                "time": _now_str(),
            }
            return

    if best.get("is_in_library"):
        _inc_stat(stats, src_name, STATUS_IN_LIBRARY)
        new_handled[seed] = {
            "status": STATUS_IN_LIBRARY,
            "tmdb_id": tmdb_id,
            "media_type": media_type,
            "time": _now_str(),
        }
        return

    # 创建订阅：远端明确成功后才写入本地。
    async with db_lock:
        try:
            outcome, sub = await _create_subscription(db, nf_service, tmdb_id, matched_title, media_type, poster, year)
            if outcome == "created" and sub:
                _inc_stat(stats, src_name, STATUS_SUBSCRIBED)
                added.append({"tmdb_id": tmdb_id, "title": matched_title, "source": src_name, "media_type": media_type})
                new_handled[seed] = {
                    "status": STATUS_SUBSCRIBED,
                    "tmdb_id": tmdb_id,
                    "media_type": media_type,
                    "time": _now_str(),
                }
                logger.info(f"[自动订阅] 新增订阅: {matched_title} (tmdb_id={tmdb_id}, 来源={src_name})")
            elif outcome == "already_exists" and sub:
                _inc_stat(stats, src_name, STATUS_EXISTS)
                new_handled[seed] = {
                    "status": STATUS_EXISTS,
                    "tmdb_id": tmdb_id,
                    "media_type": media_type,
                    "time": _now_str(),
                }
                logger.info(f"[自动订阅] NextFind 已有订阅，已同步本地记录: {matched_title}")
            elif outcome == "local_exists":
                _inc_stat(stats, src_name, STATUS_EXISTS)
                new_handled[seed] = {
                    "status": STATUS_EXISTS,
                    "tmdb_id": tmdb_id,
                    "media_type": media_type,
                    "time": _now_str(),
                }
            else:
                _inc_stat(stats, src_name, STATUS_ERROR)
                new_handled[seed] = {"status": STATUS_ERROR, "time": _now_str()}
        except Exception as e:
            logger.error(f"[自动订阅] 订阅失败: {title}: {e}")
            _inc_stat(stats, src_name, STATUS_ERROR)
            new_handled[seed] = {"status": STATUS_ERROR, "time": _now_str()}


async def _create_subscription(
    db: AsyncSession,
    nf_service: NextFindService,
    tmdb_id: int,
    title: str,
    media_type: str,
    poster: str | None,
    year: str | None,
) -> tuple[str, Subscription | None]:
    """确认 NextFind 订阅后再创建本地订阅记录。"""
    existing = await db.execute(select(Subscription).where(Subscription.tmdb_id == tmdb_id))
    if existing.scalar_one_or_none():
        return "local_exists", None

    remote = await nf_service.create_subscription(tmdb_id, media_type)
    if remote.outcome == "failed":
        logger.error(
            "[自动订阅] NextFind 未确认订阅: tmdb_id=%s, reason=%s",
            tmdb_id,
            remote.message,
        )
        return "failed", None

    year_int = int(year) if year and year.isdigit() else None
    sub = Subscription(
        id=str(uuid.uuid4()),
        tmdb_id=tmdb_id,
        media_type=media_type,
        title=title,
        poster_url=poster,
        year=year_int,
        nf_subscribed=True,
        nf_sub_id=remote.subscription_id,
        nf_status=None,
        nf_missing_eps=0,
        source="auto_subscribe",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(sub)
    db.add(
        ActivityLog(
            id=str(uuid.uuid4()),
            action="subscribe",
            tmdb_id=tmdb_id,
            message=f"自动订阅: {title} ({media_type})",
            created_at=datetime.now(UTC),
        )
    )
    try:
        await db.commit()
        await db.refresh(sub)
    except Exception:
        await db.rollback()
        logger.exception("[自动订阅] NextFind 已成功但本地持久化失败: tmdb_id=%s", tmdb_id)
        raise
    return remote.outcome, sub


def _source_options(cfg: dict, src_name: str) -> dict:
    """提取每源的配置子集。"""
    prefix = f"{src_name}_"
    opts = {}
    for k, v in cfg.items():
        if k.startswith(prefix) or k in ("nf_cache", "proxy_url"):
            opts[k] = v
    return opts


def _passes_global_filter(cfg: dict, item: RankMediaItem) -> bool:
    """全局过滤检查。"""
    media_type = cfg.get("media_type", "all")
    if media_type != "all" and item.type_hint and item.type_hint != media_type:
        return False

    min_year = cfg.get("min_year", 0) or 0
    if min_year > 0 and item.year:
        try:
            if int(item.year) < min_year:
                return False
        except ValueError:
            pass

    return True


def _passes_source_filter(cfg: dict, src_name: str, item: RankMediaItem) -> bool:
    """每源过滤检查。"""
    prefix = f"{src_name}_"
    media_type = cfg.get(f"{prefix}media_type", "all")
    if media_type and media_type != "all" and item.type_hint and item.type_hint != media_type:
        return False

    min_year = cfg.get(f"{prefix}min_year", 0) or 0
    if min_year > 0 and item.year:
        try:
            if int(item.year) < min_year:
                return False
        except ValueError:
            pass

    return True


def _pick_best(results: list[dict], title: str, type_hint: str, item_year: str | None = None) -> dict | None:
    """从搜索结果中选择最佳匹配。

    匹配策略（参考 AWBotNest）:
        1. 类型过滤：type_hint 明确时优先同类型候选
        2. 精确标题匹配（忽略大小写，忽略全角/半角标点差异）
        3. 基础标题匹配：剥离季节、数字尾缀后再精确匹配
        4. 年份精确/±1 年就近匹配
        5. 子串匹配（查询词长度 >= 3 时启用）
        6. 取评分最高的
    """
    if not results:
        return None

    title_lower = title.strip().lower()

    def _r_title(r: dict) -> str:
        return (r.get("title") or r.get("name") or "").strip().lower()

    def _r_type(r: dict) -> str:
        return (r.get("raw_type") or r.get("media_type") or "").lower()

    def _r_year(r: dict) -> int | None:
        y = r.get("year") or ""
        try:
            return int(str(y)[:4]) if y else None
        except (ValueError, TypeError):
            return None

    def _normalize(s: str) -> str:
        """归一化：全角/半角标点统一、多余空格去除。"""
        s = s.replace("，", ",").replace("？", "?").replace("！", "!").replace("。", ".")
        s = s.replace("（", "(").replace("）", ")").replace("、", ",").replace(" ", "")
        return s

    def _strip_season(s: str) -> str:
        """剥离季节后缀、副标题和末尾数字。"""
        s = re.sub(r"[第][一二三四五六七八九十百\d]+[季]", "", s).strip()
        s = re.sub(r"[\s\-_]*\d{1,4}$", "", s).strip()
        # 剥离冒号副标题："复仇者联盟5：毁灭之日" → "复仇者联盟5"
        s = re.split(r"[：:]\s*", s, maxsplit=1)[0].strip()
        return s

    # 按类型过滤候选
    candidates = results
    if type_hint in ("movie", "tv"):
        typed = [r for r in results if _r_type(r) == type_hint]
        candidates = typed or results

    # 归一化的查询标题
    norm_title = _normalize(title_lower)
    stripped_base = _strip_season(norm_title)

    # 阶段 1: 同类型 + 归一化精确匹配（同名候选优先按年份消歧）
    exact = [r for r in candidates if _normalize(_r_title(r)) == norm_title]
    if exact:
        return _best_by_year_then_vote(exact, item_year)

    # 阶段 2: 同类型 + 基础标题精确匹配（剥离季节/数字后缀）
    if stripped_base and stripped_base != norm_title:
        base_exact = [r for r in candidates if _normalize(_r_title(r)) == stripped_base]
        if base_exact:
            return _best_by_year_then_vote(base_exact, item_year)

    # 阶段 3: 年份就近匹配
    if type_hint in ("movie", "tv"):
        want_year = _pick_year(item_year, [_r_year(r) for r in candidates])
        if want_year is not None:
            year_exact = [r for r in candidates if _r_year(r) == want_year]
            if year_exact:
                return _best_by_vote(year_exact)
            year_near = [r for r in candidates if _r_year(r) is not None and abs(_r_year(r) - want_year) <= 1]
            if year_near:
                return _best_by_vote(year_near)

    # 阶段 4: 子串匹配（仅当查询词长度 >= 3）
    if len(title_lower) >= 3:
        substr = [r for r in candidates if title_lower in _r_title(r) or _r_title(r) in title_lower]
        if substr:
            return _best_by_vote(substr)

    # 阶段 5: 无匹配，取评分最高的
    return _best_by_vote(candidates)


def _pick_year(item_year: str | None, result_years: list[int | None]) -> int | None:
    """从候选结果年份中选取最合理的匹配年份。"""
    if item_year:
        try:
            return int(str(item_year)[:4])
        except (ValueError, TypeError):
            pass
    # 取出现最多的年份
    valid = [y for y in result_years if y is not None]
    if not valid:
        return None
    return Counter(valid).most_common(1)[0][0]


def _best_by_year_then_vote(results: list[dict], item_year: str | None) -> dict:
    """优先按源年份匹配，再以评分选择同年候选。"""
    if item_year:
        try:
            want_year = int(str(item_year)[:4])
            exact = [r for r in results if str(r.get("year") or "")[:4] == str(want_year)]
            if exact:
                return _best_by_vote(exact)
            near = [
                r
                for r in results
                if str(r.get("year") or "")[:4].isdigit() and abs(int(str(r.get("year"))[:4]) - want_year) <= 1
            ]
            if near:
                return _best_by_vote(near)
        except (ValueError, TypeError):
            pass
    return _best_by_vote(results)


def _best_by_vote(results: list[dict]) -> dict:
    """从结果列表中取评分最高的。"""
    best = results[0]
    best_vote = float(best.get("vote_average") or best.get("_vote_average") or 0)
    for r in results[1:]:
        vote = float(r.get("vote_average") or r.get("_vote_average") or 0)
        if vote > best_vote:
            best_vote = vote
            best = r
    return best


def _title_similar_enough(source_title: str, matched_title: str) -> bool:
    """校验搜索标题与匹配标题是否足够相似，防止完全不相关的误匹配。

    对于中文标题，要求至少 2 个共同汉字（且长度 >= 2 时匹配比例 >= 30%）；
    对于英文标题，要求单词重叠度 >= 50%。
    纯数字/过短标题（< 2 字符）跳过校验（依赖其他过滤逻辑）。
    """
    src = source_title.strip().lower()
    mtd = matched_title.strip().lower()
    if not src or not mtd:
        return False

    # 过短标题跳过（如"八仙"之类短名）
    if len(src) < 2 or len(mtd) < 2:
        return True

    # 判断是否为中文为主
    cn_chars_src = sum(1 for c in src if "一" <= c <= "鿿")
    cn_chars_mtd = sum(1 for c in mtd if "一" <= c <= "鿿")

    if cn_chars_src >= 2 or cn_chars_mtd >= 2:
        # 中文标题：取共同汉字集合
        src_set = {c for c in src if "一" <= c <= "鿿"}
        mtd_set = {c for c in mtd if "一" <= c <= "鿿"}
        if not src_set or not mtd_set:
            return False
        common = src_set & mtd_set
        # 至少 2 个共同汉字，且占较短方比例 >= 30%
        min_len = min(len(src_set), len(mtd_set))
        return len(common) >= 2 and len(common) / min_len >= 0.3
    else:
        # 英文标题：单词级重叠
        src_words = set(src.replace("-", " ").replace(":", " ").split())
        mtd_words = set(mtd.replace("-", " ").replace(":", " ").split())
        if not src_words or not mtd_words:
            return True
        common = src_words & mtd_words
        return len(common) / min(len(src_words), len(mtd_words)) >= 0.5


def _inc_stat(stats: dict, src_name: str, status: str):
    """递增统计计数器。"""
    s = stats.setdefault(src_name, {})
    s[status] = s.get(status, 0) + 1


def _now_str() -> str:
    return datetime.now(UTC).isoformat()
