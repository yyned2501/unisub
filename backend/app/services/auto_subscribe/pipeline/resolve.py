"""自动订阅 — 单条目搜索 + 匹配解析（搜索词变体 → 候选池 → 精确优先 → 相似度门槛 → JEV 闸门）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.auto_subscribe.models import (
    REASON_AI_EMPTY,
    REASON_GATE_REJECT,
    REASON_NO_CANDIDATES,
    REASON_SIMILARITY_REJECT,
    RankMediaItem,
)
from app.services.auto_subscribe.pipeline.matching import (
    judge_candidate,
    pick_best_exact,
    pick_best_fallback,
    pick_best_with_verdict,
    title_overlap_ratio,
    title_similar_enough,
)
from app.services.auto_subscribe.pipeline.search import (
    collect_candidates,
    run_fallback_chain,
    search_tmdb_or_nf,
)
from app.services.bangumi import BangumiService
from app.services.decision import GateVerdict
from app.services.decision_payload import candidate_title
from app.services.nextfind import NextFindService
from app.services.tmdb import TMDBService

# 未识别时回填给历史的候选标题数（「当时 TMDB 返回了什么」）
_TOP_CANDIDATE_LIMIT = 3


def build_search_queries(title: str) -> list[str]:
    """构建搜索词变体列表（按优先级排序，越靠前越可信）。

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
        - 空格/全角空格/「·」「・」「-」分隔的副标题：追加首段
          （"怪兽8号 鸣海的平日" → "怪兽8号"）
        - 「～…～」「~…~」「〜…〜」「「…」」包裹段：追加剥离后的主干
          （"桃源暗鬼 ～日光・华严之泷篇～" → "桃源暗鬼"）
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

    # 空格/全角空格/「·」「・」「-」分隔的副标题：追加首段（最低优先级）
    # 「剧场版 xxx」已由上面的前缀规则处理，这里再取首段只会得到「剧场版」这种垃圾搜索词
    if not title.startswith(("剧场版", "劇場版")):
        parts = re.split(r"[\s\u3000·・\-]+", title, maxsplit=1)
        if len(parts) > 1:
            head = parts[0].strip().strip("。：:·・~～-")
            if len(head) >= 2:
                _add(head)

    # 「～…～」「「…」」包裹段：追加剥离后的主干（最低优先级）
    unwrapped = re.sub(r"[～~〜][^～~〜]*[～~〜]", " ", title)
    unwrapped = re.sub(r"「[^」]*」", " ", unwrapped)
    unwrapped = re.sub(r"\s+", " ", unwrapped).strip()
    if unwrapped != title and len(unwrapped) >= 2:
        _add(unwrapped)

    return queries


@dataclass
class ResolveOutcome:
    """resolve_best_match 的结论：命中的候选 + 未命中时的归因。"""

    best: dict | None = None
    reason: str = ""
    variant: str = ""
    top_candidates: list[str] = field(default_factory=list)


async def resolve_best_match(
    item: RankMediaItem,
    type_hint: str,
    nf_service: NextFindService,
    tmdb_service: TMDBService | None,
) -> ResolveOutcome:
    """对一个条目执行完整的搜索 + 匹配解析，返回结论（未命中时带归因）。

    流程：
        1. Bangumi 年份补充（动画条目 item.year 为空时）
        2. 构建搜索词变体 → 候选池（多轮搜索的并集，不再「第一个非空即返回」）
        3. 候选池：精确优先 → 相似度进池门槛 → 阶段 4/5 + JEV 闸门
        4. 主池不中 → fallback 链（Bangumi 原名/别名 → AI 兜底），结果同样走第 3 步；
           AI 结果与原标题字面不重叠时视为「疑换作品」，只有 JEV 判同一部作品才采纳
        5. 仍不中 → 返回归因（无候选 / 相似度不足 / 闸门判非同一作品 / AI 侧故障）
    """
    title = item.title
    bgm_subject = await _enrich_year_from_bangumi(item)
    queries = build_search_queries(title)
    pool, variant_map = await _search_with_variants(queries, type_hint, nf_service, tmdb_service)

    best, reason, variant = await _match_from_pool(pool, title, type_hint, item.year, variant_map)
    if best is not None:
        return ResolveOutcome(best=best, variant=variant)

    fallback = await run_fallback_chain(title, item, bgm_subject, type_hint, nf_service, tmdb_service)
    if fallback.results and fallback.ai_low_overlap:
        # AI 识别结果与原标题字面不重叠 = 疑「换了作品」：字面相似度无权放行，
        # 只有 JEV 明确判「同一部作品」才采纳；JEV 不可用（降级/影子）时整池丢弃
        # —— 宁可不订阅，也不误订（实测 `巴黎绽放的星辰` → `艾米丽在巴黎`）。
        best, variant = await _match_unverified_pool(
            fallback.results, title, type_hint, item.year, fallback.variant_map
        )
        if best is not None:
            return ResolveOutcome(best=best, variant=variant)
        top_pool = pool
    elif fallback.results:
        best, reason, variant = await _match_from_pool(
            fallback.results, title, type_hint, item.year, fallback.variant_map
        )
        if best is not None:
            return ResolveOutcome(best=best, variant=variant)
        top_pool = fallback.results
    else:
        top_pool = pool
        # 归因优先反映「候选被否」这一主因：只有主池本来就空（真·无候选）时，
        # AI 侧故障才算根因，否则会把「有候选但全被否」误报成「AI 无结果」。
        if not pool and fallback.ai_failed:
            reason = REASON_AI_EMPTY

    return ResolveOutcome(reason=reason, variant=variant, top_candidates=_top_titles(top_pool))


async def _match_unverified_pool(
    pool: list[dict],
    title: str,
    type_hint: str,
    item_year: str | None,
    variant_map: dict[str, str],
) -> tuple[dict | None, str]:
    """AI 兜底产出、且与原标题字面不重叠的候选：只有 JEV 明确判同一部作品才采纳。

    这类候选「字面不像」有两种可能：译名/写法差异（该救回）或 AI 认错了作品（该丢弃），
    字面相似度无权裁决 —— 交给 JEV。JEV 不可用（降级/影子）时按「无法确认」处理，
    返回 None（上层归因给 ``no_candidates``）。
    """
    picked = pick_best_exact(pool, title, type_hint, item_year) or pick_best_fallback(pool, title, type_hint, item_year)
    if picked is None:
        return None, ""
    verdict = await judge_candidate(title, type_hint, item_year, picked)
    if verdict.verdict is GateVerdict.PASS and not verdict.shadow:
        return picked, _variant_of(picked, variant_map)
    return None, ""


async def _match_from_pool(
    pool: list[dict],
    title: str,
    type_hint: str,
    item_year: str | None,
    variant_map: dict[str, str],
) -> tuple[dict | None, str, str]:
    """候选池 → 最佳匹配，返回 (候选, 未命中归因, 命中的搜索词)。

    顺序即防线：精确优先（零成本）→ 相似度进池门槛 → 阶段 4/5 + JEV 闸门。
    相似度只决定「谁进池」，不再事后否决 JEV 判过同一部作品的候选。
    """
    if not pool:
        return None, REASON_NO_CANDIDATES, ""

    # ⓪ 按字面相似度降序重排（稳定排序，同分保持变体优先级）：阶段 1~3 的
    #    「年份就近」在 item_year 为空时会退化成「出现最多的年份」，不重排就会
    #    把先入池的垃圾候选顶上来（线上实测：魔法姐妹露露特莉莉 → 破产姐妹）。
    ranked = sorted(pool, key=lambda r: title_overlap_ratio(title, candidate_title(r)), reverse=True)

    # ① 精确优先（阶段 1~3，零成本）：命中后仍要过字面相似度，否则阶段 3 的
    #    「年份就近」会把垃圾候选顶上来（本轮 R2 的「乱马½」正是这条路径）。
    exact = pick_best_exact(ranked, title, type_hint, item_year)
    if exact is not None and title_similar_enough(title, candidate_title(exact)):
        return exact, "", _variant_of(exact, variant_map)

    # ② 相似度进池门槛：把垃圾候选挡在池外，剩下的才值得付 JEV 的钱
    filtered = [r for r in ranked if title_similar_enough(title, candidate_title(r))]
    if filtered:
        picked, verdict = await pick_best_with_verdict(filtered, title, type_hint, item_year)
        if picked is None:
            return None, REASON_SIMILARITY_REJECT, ""
        if verdict is not None and verdict.verdict is GateVerdict.REJECT:
            return None, REASON_GATE_REJECT, _variant_of(picked, variant_map)
        return picked, "", _variant_of(picked, variant_map)

    # ③ 一个候选都不过字面相似度：只有 JEV 明确判「同一部作品」才采纳
    #    （译名/写法差异类）。影子判定与降级都不算，否则等于重新放开误订。
    picked = pick_best_fallback(pool, title, type_hint, item_year)
    if picked is not None:
        verdict = await judge_candidate(title, type_hint, item_year, picked)
        if verdict.verdict is GateVerdict.PASS and not verdict.shadow:
            return picked, "", _variant_of(picked, variant_map)
    return None, REASON_SIMILARITY_REJECT, _variant_of(picked, variant_map)


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
) -> tuple[list[dict], dict[str, str]]:
    """遍历搜索词变体多轮搜索，把结果合并成一个候选池（保序去重）。

    指定类别的变体全部无结果时才用 all 兜底。
    Returns:
        (候选池, {候选 id: 命中它的搜索词})
    """
    pool: list[dict] = []
    variant_map: dict[str, str] = {}
    typed_search_types = [type_hint] if type_hint in ("movie", "tv") else ["all"]
    for search_type in typed_search_types:
        for query in queries:
            collect_candidates(
                pool, variant_map, query, await search_tmdb_or_nf(query, search_type, nf_service, tmdb_service)
            )

    if not pool and type_hint in ("movie", "tv"):
        for query in queries:
            collect_candidates(
                pool, variant_map, query, await search_tmdb_or_nf(query, "all", nf_service, tmdb_service)
            )

    return pool, variant_map


def _variant_of(candidate: dict | None, variant_map: dict[str, str]) -> str:
    """命中候选对应的搜索词（候选缺 id 时按标题回查）。"""
    if not candidate:
        return ""
    rid = candidate.get("id")
    if rid is not None:
        found = variant_map.get(str(rid))
        if found:
            return found
    return variant_map.get(candidate_title(candidate), "")


def _top_titles(pool: list[dict]) -> list[str]:
    """候选池前 N 个标题，供历史界面展示「当时看到了什么」。"""
    return [t for t in (candidate_title(r) for r in pool[:_TOP_CANDIDATE_LIMIT]) if t]
