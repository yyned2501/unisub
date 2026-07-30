"""自动订阅 — 搜索引擎：TMDB/NF 搜索 + Bangumi 辅助 + AI 辅助识别。"""

from __future__ import annotations

import json
import re

import httpx

from app.core.logger import init_logger
from app.services.ai_config import get_ai_config_store
from app.services.auto_subscribe.models import RankMediaItem
from app.services.bangumi import BangumiService
from app.services.nextfind import NextFindAuthError, NextFindService
from app.services.tmdb import TMDBService

logger = init_logger(__name__)


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
) -> list[dict] | None:
    """fallback 链：Bangumi 候选标题 → AI 辅助识别。

    仅在主搜索无结果时调用，依次尝试：
    1. Bangumi 候选项（已有 bgm_subject 且为动画时）
    2. AI 辅助识别（ai_assist_enabled 开启时）
    """
    # 1. Bangumi 候选标题辅助搜索
    result = await _bangumi_assisted_search(title, bgm_subject, type_hint, nf_service, tmdb_service)
    if result:
        logger.info(f"[自动订阅] Bangumi 辅助搜索成功: {title}")
        return result

    # 2. AI 辅助识别
    result = await _ai_assisted_search(title, item, type_hint, nf_service, tmdb_service)
    if result:
        logger.info(f"[自动订阅] AI 辅助识别成功: {title}")
        return result

    return None


# ── 内部实现 ──────────────────────────────────────────────


async def _bangumi_assisted_search(
    title: str,
    bgm_subject: dict | None,
    type_hint: str,
    nf_service: NextFindService,
    tmdb_service: TMDBService | None,
) -> list[dict] | None:
    """Bangumi 候选标题辅助搜索：用现有 bgm_subject 的别名扩展搜索。"""
    if not bgm_subject:
        return None
    bangumi_svc = BangumiService()
    if not bangumi_svc.is_anime(bgm_subject):
        return None
    candidates = bangumi_svc.get_candidate_titles(bgm_subject)
    # 去掉已经在搜索词里用过的原始标题
    candidates = [c for c in candidates if c != title]
    if not candidates:
        return None

    logger.info(f"[自动订阅] Bangumi 辅助搜索: {title} → {candidates[:3]}")
    search_types = [type_hint] if type_hint in ("movie", "tv") else ["all"]
    for search_type in search_types:
        for candidate in candidates:
            result = await search_tmdb_or_nf(candidate, search_type, nf_service, tmdb_service)
            if result:
                return result
    return None


async def _ai_assisted_search(
    title: str,
    item: RankMediaItem,
    type_hint: str,
    nf_service: NextFindService,
    tmdb_service: TMDBService | None,
) -> list[dict] | None:
    """AI 辅助识别：调用 LLM 解析媒体标题，再用 TMDB 验证结果。"""
    ai_config = get_ai_config_store().load_config()
    ai_enabled = ai_config["ai_assist_enabled"]
    if not ai_enabled:
        return None

    api_key = ai_config["ai_api_key"]
    api_base = ai_config["ai_api_base"]
    model = ai_config["ai_model"] or "gpt-4o-mini"
    if not api_key or not api_base:
        logger.warning("[自动订阅] AI 辅助已启用但缺少 ai_api_key 或 ai_api_base")
        return None

    # 构建 prompt
    prompt = (
        "你是一个媒体识别助手。请根据用户提供的标题文本，识别出对应的媒体名称。\n\n"
        f"标题: {title}\n"
        f"类别提示: {type_hint if type_hint in ('movie', 'tv') else '未知'}\n"
        f"附加信息: 年份={item.year or '未知'}"
    )
    if item.bangumi_id:
        prompt += f", Bangumi ID={item.bangumi_id}"
    if item.douban_id:
        prompt += f", 豆瓣 ID={item.douban_id}"
    prompt += (
        "\n\n请返回 JSON 格式，不要包含额外文字:\n"
        '{"title": "标准化的媒体名称", "media_type": "movie|tv", "season": 1, "year": "2024"}\n'
        "其中 season 仅在 media_type 为 tv 且涉及特定季时填写，否则为 null。"
    )

    logger.info(f"[自动订阅] AI 辅助识别: {title}")
    try:
        text = await _call_llm(prompt, api_base, api_key, model)
        if not text:
            return None
    except Exception as e:
        logger.warning(f"[自动订阅] AI 调用失败: {title}: {e}")
        return None

    parsed = _parse_ai_media(text)
    if not parsed:
        logger.warning(f"[自动订阅] AI 返回格式异常: {title}, raw={text[:200]}")
        return None

    ai_title = parsed["title"]
    ai_type = parsed["media_type"]
    logger.info(f"[自动订阅] AI 识别结果: {ai_title} ({ai_type})")

    # 用 TMDB 验证 AI 识别结果
    search_type = ai_type if type_hint in ("movie", "tv", "all") else "all"
    result = await search_tmdb_or_nf(ai_title, search_type, nf_service, tmdb_service)
    if result:
        return result

    # 如果指定类型没搜到，用 all 兜底
    if search_type != "all":
        result = await search_tmdb_or_nf(ai_title, "all", nf_service, tmdb_service)
        if result:
            return result

    return None


async def _call_llm(
    prompt: str,
    api_base: str,
    api_key: str,
    model: str,
    timeout: int = 30,
) -> str | None:
    """调用 openai 兼容的 LLM API 并返回文本响应。"""
    base = api_base.rstrip("/")
    url = f"{base}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 300,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout), follow_redirects=True) as client:
        response = await client.post(url, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()
    choices = data.get("choices")
    if not choices:
        return None
    content = choices[0].get("message", {}).get("content", "").strip()
    return content or None


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
