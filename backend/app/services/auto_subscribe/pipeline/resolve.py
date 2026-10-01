"""自动订阅 — 单条目搜索 + 匹配解析（搜索词变体 → 多轮搜索 → fallback → 最佳匹配 → 相似度校验）。"""

from __future__ import annotations

import re

from app.services.auto_subscribe.models import RankMediaItem
from app.services.auto_subscribe.pipeline.matching import pick_best_gated, title_similar_enough
from app.services.auto_subscribe.pipeline.search import run_fallback_chain, search_tmdb_or_nf
from app.services.bangumi import BangumiService
from app.services.nextfind import NextFindService
from app.services.tmdb import TMDBService


def build_search_queries(title: str) -> list[str]:
    """构建搜索词变体列表。

    规则：
        - 含 "第X季" 后缀：剥离季节后缀，仅用基础标题搜索
        - 含中文句号「。」分割的副标题：追加句号前部分
          （"靠死亡游戏混饭吃。 44:CLOUDY BEACH" → "靠死亡游戏混饭吃"）
        - 含冒号副标题：追加冒号前部分（"复仇者联盟5：毁灭之日" → "复仇者联盟5"）
        - 含「第X章/篇/话/部分」等分段标识：追加分段前部分
          （"剧场版 鬼灭之刃 无限城篇 第一章 猗窝座再袭" → "剧场版 鬼灭之刃 无限城篇"；
          "铠真传 武士军团 第2部分" → "铠真传 武士军团"）
        - 以「剧场版/劇場版」开头：追加移除前缀的变体
        - 数字结尾：追加剥离末尾数字的基础名（保留完整名在前）
        - 变体去重
    """
    queries: list[str] = [title]

    season_match = re.search(r"[第]([一二三四五六七八九十百\d]+)[季]", title)
    if season_match:
        # 剧集类标题：剥离季节后缀，仅用基础标题搜索
        base_title = title[: season_match.start()].strip()
        if base_title:
            return [base_title]
        return queries

    seen: set[str] = {title}

    def _add(v: str) -> None:
        v = v.strip()
        if v and v not in seen:
            seen.add(v)
            queries.append(v)

    # 中文句号「。」分割副标题
    if "。" in title:
        period_idx = title.index("。")
        if period_idx < len(title) - 1 and title[period_idx + 1 :].strip():
            before_period = title[:period_idx].strip()
            if len(before_period) >= 2:
                _add(before_period)

    # 冒号分割副标题
    colon_parts = re.split(r"[：:]\s*", title, maxsplit=1)
    if len(colon_parts) > 1 and len(colon_parts[0]) >= 2:
        _add(colon_parts[0].strip())

    # 「第X章/篇/话/部分」分段标识（数字或中文数词紧跟在「第」后）
    chapter_match = re.search(r"第([一二三四五六七八九十百\d]+)(?:章|篇|话|部分)", title)
    if chapter_match:
        base = title[: chapter_match.start()].strip()
        if len(base) >= 2:
            _add(base)

    # 「剧场版/劇場版」前缀；同时组合处理后续章节标识
    for prefix in ("剧场版", "劇場版"):
        if title.startswith(prefix):
            rest = title[len(prefix) :].strip()
            if len(rest) >= 2:
                _add(rest)
            rest_chapter = re.search(r"第([一二三四五六七八九十百\d]+)(?:章|篇|话|部分)", rest)
            if rest_chapter:
                _add(rest[: rest_chapter.start()])
            break

    # 数字结尾标题先保留完整名称搜索；无候选时才剥离后缀重试
    numeric_tail = re.search(r"(\d{1,4})$", title)
    if numeric_tail:
        base_title = title[: numeric_tail.start()].strip()
        if len(base_title) >= 2:
            _add(base_title)

    return queries


async def resolve_best_match(
    item: RankMediaItem,
    type_hint: str,
    nf_service: NextFindService,
    tmdb_service: TMDBService | None,
) -> dict | None:
    """对一个条目执行完整的搜索 + 匹配解析，返回最佳匹配结果或 None。

    流程：
        1. Bangumi 年份补充（动画条目 item.year 为空时）
        2. 构建搜索词变体并多轮搜索（指定类别优先，all 兜底）
        3. 主搜索无结果 → fallback 链（Bangumi 别名 → AI 辅助识别）
        4. 选取最佳匹配；未命中或相似度不足时用 fallback 结果重试
    """
    title = item.title
    bgm_subject = await _enrich_year_from_bangumi(item)
    queries = build_search_queries(title)
    results = await _search_with_variants(queries, type_hint, nf_service, tmdb_service)

    # fallback 结果记忆化，多次重试只跑一次 fallback 链
    fallback_result: list[dict] | None = None

    async def get_fallback() -> list[dict] | None:
        nonlocal fallback_result
        if fallback_result is None:
            fallback_result = await run_fallback_chain(title, item, bgm_subject, type_hint, nf_service, tmdb_service)
        return fallback_result

    if not results:
        results = await get_fallback()
    if not results:
        return None

    best = await pick_best_gated(results, title, type_hint, item.year)
    if not best:
        fallback = await get_fallback()
        if fallback:
            best = await pick_best_gated(fallback, title, type_hint, item.year)
    if not best:
        return None

    # 标题相似度校验：防止完全不匹配的条目被错误订阅
    best_title = (best.get("title") or best.get("name") or "").strip()
    if best_title and not title_similar_enough(title, best_title):
        fallback = await get_fallback()
        if fallback:
            best = await pick_best_gated(fallback, title, type_hint, item.year)
            best_title = (best.get("title") or best.get("name") or "").strip() if best else ""
        if not best or not best_title or not title_similar_enough(title, best_title):
            return None

    return best


async def _enrich_year_from_bangumi(item: RankMediaItem) -> dict | None:
    """动画条目通过 Bangumi 补充年份（item.year 为空时），并返回 subject 缓存供 fallback 链复用。"""
    if not (item.bangumi_id or item.source_meta.get("bangumi_id")):
        return None
    bgm_id = item.bangumi_id or item.source_meta["bangumi_id"]
    bangumi_svc = BangumiService()
    bgm_subject = await bangumi_svc.get_subject(bgm_id)
    if bgm_subject and bangumi_svc.is_anime(bgm_subject) and not item.year:
        bgm_year = bangumi_svc.get_year(bgm_subject)
        if bgm_year:
            item.year = bgm_year
    return bgm_subject


async def _search_with_variants(
    queries: list[str],
    type_hint: str,
    nf_service: NextFindService,
    tmdb_service: TMDBService | None,
) -> list[dict] | None:
    """遍历搜索词变体多轮搜索；指定类别均无结果时用 all 兜底。"""
    typed_search_types = [type_hint] if type_hint in ("movie", "tv") else ["all"]
    for search_type in typed_search_types:
        for query in queries:
            results = await search_tmdb_or_nf(query, search_type, nf_service, tmdb_service)
            if results:
                return results

    if type_hint in ("movie", "tv"):
        for query in queries:
            results = await search_tmdb_or_nf(query, "all", nf_service, tmdb_service)
            if results:
                return results

    return None
