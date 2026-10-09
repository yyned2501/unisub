"""自动订阅 — 搜索引擎：TMDB/NF 搜索 + Bangumi 辅助 + AI 辅助识别。"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from app.core.http_client import HttpRequestError, http_client
from app.core.logger import init_logger
from app.services.ai_config import get_ai_config_store
from app.services.auto_subscribe.models import RankMediaItem
from app.services.bangumi import BangumiService
from app.services.nextfind import NextFindAuthError, NextFindService
from app.services.tmdb import TMDBService

logger = init_logger(__name__)


@dataclass
class FallbackOutcome:
    """fallback 链的结论：候选池 + 命中来源 + AI 是否失败。

    ``ai_failed`` 只表示「AI 兜底被调用且没产出可用结果」，用于把未识别
    归因到 ``ai_empty``（区分「压根没候选」与「AI 挂了」）。
    """

    results: list[dict] = field(default_factory=list)
    variant_map: dict[str, str] = field(default_factory=dict)
    ai_failed: bool = False


def collect_candidates(
    pool: list[dict],
    variant_map: dict[str, str],
    query: str,
    results: list[dict] | None,
) -> None:
    """把一次搜索的结果并入候选池：按 id（缺失时按标题）保序去重，并记录命中的搜索词。

    候选池是「多轮搜索的并集」而非「第一个非空结果」——只看第一个非空结果会
    让后面的变体永远没机会命中（译名差异类的漏配根因）。
    """
    for r in results or []:
        rid = r.get("id")
        key = str(rid) if rid is not None else (r.get("title") or r.get("name") or "").strip()
        if not key or key in variant_map:
            continue
        pool.append(r)
        variant_map[key] = query


async def search_tmdb_or_nf(
    query: str,
    search_type: str,
    nf_service: NextFindService,
    tmdb_service: TMDBService | None,
) -> list[dict] | None:
    """对单一查询词优先搜 TMDB，空结果时回退 NextFind。"""
    if tmdb_service:
        try:
            tmdb_results = await tmdb_service.search(query, search_type)
            if tmdb_results:
                return tmdb_results
        except Exception as e:
            logger.warning(f"[自动订阅] TMDB 搜索异常: {query}: {e}")
    try:
        nf_results = await nf_service.search_tmdb(query, search_type)
        if nf_results:
            return nf_results
    except NextFindAuthError:
        raise
    except Exception as e:
        logger.warning(f"[自动订阅] NF 搜索异常: {query}: {e}")
    return None


async def run_fallback_chain(
    title: str,
    item: RankMediaItem,
    bgm_subject: dict | None,
    type_hint: str,
    nf_service: NextFindService,
    tmdb_service: TMDBService | None,
) -> FallbackOutcome:
    """fallback 链：Bangumi 候选标题 → AI 辅助识别。

    仅在主搜索候选池无法命中时调用，依次尝试：
    1. Bangumi 候选项（已有 bgm_subject 且为动画时）
    2. AI 辅助识别（ai_assist_enabled 开启时）

    Returns:
        :class:`FallbackOutcome`：候选池为空表示链上没有可用结果；
        ``ai_failed`` 为真表示 AI 兜底被调用过但没产出结果。
    """
    # 1. Bangumi 候选标题辅助搜索
    pool, variant_map = await _bangumi_assisted_search(title, bgm_subject, type_hint, nf_service, tmdb_service)
    if pool:
        logger.info(f"[自动订阅] Bangumi 辅助搜索成功: {title}")
        return FallbackOutcome(results=pool, variant_map=variant_map)

    # 2. AI 辅助识别
    pool, variant_map, ai_failed = await _ai_assisted_search(title, item, type_hint, nf_service, tmdb_service)
    if pool:
        logger.info(f"[自动订阅] AI 辅助识别成功: {title}")
        return FallbackOutcome(results=pool, variant_map=variant_map)

    return FallbackOutcome(ai_failed=ai_failed)


# ── 内部实现 ──────────────────────────────────────────────


async def _bangumi_assisted_search(
    title: str,
    bgm_subject: dict | None,
    type_hint: str,
    nf_service: NextFindService,
    tmdb_service: TMDBService | None,
) -> tuple[list[dict], dict[str, str]]:
    """Bangumi 候选标题辅助搜索：用现有 bgm_subject 的原名/别名扩展搜索。

    所有候选标题的结果并入同一个候选池（不再「第一个非空即返回」），
    这样日文原名命中的候选不会被中文译名返回的垃圾结果顶掉。
    """
    if not bgm_subject:
        return [], {}
    bangumi_svc = BangumiService()
    if not bangumi_svc.is_anime(bgm_subject):
        return [], {}
    candidates = bangumi_svc.get_candidate_titles(bgm_subject)
    # 去掉已经在搜索词里用过的原始标题
    candidates = [c for c in candidates if c != title]
    if not candidates:
        return [], {}

    logger.info(f"[自动订阅] Bangumi 辅助搜索: {title} → {candidates[:3]}")
    pool: list[dict] = []
    variant_map: dict[str, str] = {}
    search_types = [type_hint] if type_hint in ("movie", "tv") else ["all"]
    for search_type in search_types:
        for candidate in candidates:
            collect_candidates(
                pool, variant_map, candidate, await search_tmdb_or_nf(candidate, search_type, nf_service, tmdb_service)
            )
    return pool, variant_map


async def _ai_assisted_search(
    title: str,
    item: RankMediaItem,
    type_hint: str,
    nf_service: NextFindService,
    tmdb_service: TMDBService | None,
) -> tuple[list[dict], dict[str, str], bool]:
    """AI 辅助识别：调用 LLM 解析媒体标题，再用 TMDB 回搜。

    Returns:
        (候选池, 变体映射, AI 是否失败)。三种失败（空 content / 解析失败 /
        回搜无结果）都落 WARN 日志并置 ``ai_failed=True``——静默失败是上一轮
        8 条未识别里 2 条查不出原因的直接原因。
    """
    ai_config = get_ai_config_store().load_config()
    ai_enabled = ai_config["ai_assist_enabled"]
    if not ai_enabled:
        return [], {}, False

    api_key = ai_config["ai_api_key"]
    api_base = ai_config["ai_api_base"]
    model = ai_config["ai_model"] or "gpt-4o-mini"
    enable_search = ai_config.get("ai_enable_search", False)
    if not api_key or not api_base:
        logger.warning("[自动订阅] AI 兜底失败（缺少 ai_api_key 或 ai_api_base）: %s", title)
        return [], {}, True

    # 构建 prompt — 附加上下文来源信息
    source_hints = []
    src = item.source_meta.get("source", "")
    if src == "douban":
        source_hints.append("来源: 豆瓣榜单")
        if item.douban_id:
            source_hints.append(f"豆瓣 ID: {item.douban_id}")
    elif src == "maoyan":
        source_hints.append("来源: 猫眼榜单")
        mtype = item.source_meta.get("type", "")
        if mtype == "movie_box":
            source_hints.append("类型: 电影票房榜")
        elif mtype == "web_heat":
            source_hints.append("类型: 网络热度榜")
    elif src == "mikan":
        source_hints.append("来源: Mikan 新番")
        source_hints.append("类型: 动画")

    prompt = (
        "你是一个媒体识别助手。请根据用户提供的标题文本，识别出对应的媒体名称。\n\n"
        f"标题: {title}\n"
        f"类别提示: {type_hint if type_hint in ('movie', 'tv') else '未知'}\n"
    )
    if item.year:
        prompt += f"年份: {item.year}\n"
    if source_hints:
        prompt += f"{'，'.join(source_hints)}\n"
    prompt += (
        "\n请返回 JSON 格式，不要包含额外文字:\n"
        '{"title": "标准化的媒体名称", "media_type": "movie|tv", "season": 1, "year": "2024"}\n'
        "其中 season 仅在 media_type 为 tv 且涉及特定季时填写，否则为 null。"
    )

    logger.info(f"[自动订阅] AI 辅助识别: {title} (model={model})")
    started = time.monotonic()
    try:
        text, source = await _call_llm(prompt, api_base, api_key, model, enable_search=enable_search)
    except Exception as e:
        logger.warning(
            "[自动订阅] AI 兜底失败（调用异常）: %s model=%s 耗时=%.2fs: %s",
            title,
            model,
            time.monotonic() - started,
            e,
        )
        return [], {}, True
    elapsed = time.monotonic() - started

    if not text:
        logger.warning(
            "[自动订阅] AI 兜底失败（空返回，来源=%s）: %s model=%s 耗时=%.2fs", source, title, model, elapsed
        )
        return [], {}, True
    if source == "reasoning":
        logger.info("[自动订阅] AI content 为空，已从 reasoning_content 提取结果: %s", title)

    parsed = _parse_ai_media(text)
    if not parsed:
        logger.warning(
            "[自动订阅] AI 兜底失败（解析失败）: %s model=%s 耗时=%.2fs raw=%s", title, model, elapsed, text[:200]
        )
        return [], {}, True

    ai_title = parsed["title"]
    ai_type = parsed["media_type"]
    logger.info("[自动订阅] AI 识别结果: %s (%s) model=%s 耗时=%.2fs", ai_title, ai_type, model, elapsed)

    # 用 TMDB 回搜验证 AI 识别结果
    pool: list[dict] = []
    variant_map: dict[str, str] = {}
    search_type = ai_type if type_hint in ("movie", "tv", "all") else "all"
    collect_candidates(
        pool, variant_map, ai_title, await search_tmdb_or_nf(ai_title, search_type, nf_service, tmdb_service)
    )

    # 如果指定类型没搜到，用 all 兜底
    if not pool and search_type != "all":
        collect_candidates(
            pool, variant_map, ai_title, await search_tmdb_or_nf(ai_title, "all", nf_service, tmdb_service)
        )

    if not pool:
        logger.warning("[自动订阅] AI 兜底失败（回搜无结果）: %s → %s model=%s", title, ai_title, model)
        return [], {}, True

    return pool, variant_map, False


async def _call_llm(
    prompt: str,
    api_base: str,
    api_key: str,
    model: str,
    enable_search: bool = False,
) -> tuple[str, str]:
    """调用 openai 兼容的 LLM API。

    content 为空时尝试从 ``reasoning_content`` 里提取 JSON 再兜一次
    （推理类模型把结论写在 reasoning_content、content 留空的实测行为）。

    Returns:
        (可用文本, 来源)；来源为 "content" / "reasoning" / "empty" / "no_choices"，
        文本为空串表示这一路都没拿到可用内容。
    """
    base = api_base.rstrip("/")
    url = f"{base}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 300,
    }
    # Qwen 系列模型支持 enable_search 联网搜索参数
    if enable_search:
        body["enable_search"] = True
    result = await http_client.post(url, headers=headers, json=body)
    if "error" in result:
        raise HttpRequestError(result.get("detail", result["error"]))
    choices = result.get("choices")
    if not choices:
        return "", "no_choices"
    message = choices[0].get("message") or {}
    content = str(message.get("content") or "").strip()
    if content:
        return content, "content"

    reasoning = str(message.get("reasoning_content") or "")
    extracted = _extract_json_object(reasoning)
    if extracted:
        return extracted, "reasoning"
    return "", "empty"


def _extract_json_object(text: str) -> str | None:
    """从自由文本中截取首个 ``{`` 到末个 ``}`` 的片段；不是合法 JSON 时返回 None。"""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    candidate = text[start : end + 1]
    try:
        json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return candidate


def _parse_ai_media(text: str) -> dict | None:
    """解析 LLM 返回的 JSON，验证媒体识别结果。

    Returns:
        验证后的 dict，包含 title、media_type、season、year; 或 None
    """
    # 尝试从 markdown 代码块中提取 JSON
    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if code_block:
        text = code_block.group(1).strip()

    text = text.strip()
    # 尝试直接解析 JSON
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 尝试找第一个 { 到最后一个 }
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start >= 0 and brace_end > brace_start:
            try:
                data = json.loads(text[brace_start : brace_end + 1])
            except json.JSONDecodeError:
                return None
        else:
            return None

    if not isinstance(data, dict):
        return None

    title = (data.get("title") or "").strip()
    if not title or len(title) > 200:
        return None

    media_type = str(data.get("media_type") or "").lower()
    if media_type not in ("movie", "tv"):
        return None

    season = data.get("season")
    if season is not None:
        try:
            season = int(season)
            if not 1 <= season <= 200:
                season = None
        except (ValueError, TypeError):
            season = None

    year = data.get("year")
    if year is not None:
        try:
            year = str(int(str(year)[:4]))
        except (ValueError, TypeError):
            year = None

    return {"title": title, "media_type": media_type, "season": season, "year": year}
