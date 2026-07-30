"""自动订阅 — 全局、每源与搜索后过滤逻辑。"""

from __future__ import annotations

from app.core.logger import init_logger
from app.services.auto_subscribe.models import SOURCE_NAMES, RankMediaItem
from app.services.tmdb import TMDBService

logger = init_logger(__name__)


def source_options(cfg: dict, src_name: str) -> dict:
    """提取每源的配置子集。"""
    prefix = f"{src_name}_"
    opts = {}
    for k, v in cfg.items():
        if k.startswith(prefix) or k in ("nf_cache", "proxy_url"):
            opts[k] = v
    return opts


def passes_global_filter(cfg: dict, item: RankMediaItem) -> tuple[bool, str]:
    """全局过滤检查——仅检查媒体类型。

    年份过滤统一推迟到搜索后（`year_filter_reason`），基于 TMDB 准确数据判断。

    Returns:
        (通过, 原因字符串)
    """
    media_type = cfg.get("media_type", "all")
    if media_type != "all" and item.type_hint and item.type_hint != media_type:
        return False, f"全局媒体类型过滤: 配置={media_type}, 条目={item.type_hint}"

    # 年份过滤统一推迟到搜索后，基于 TMDB 准确数据判断
    return True, ""


def passes_source_filter(cfg: dict, src_name: str, item: RankMediaItem) -> tuple[bool, str]:
    """每源过滤检查——仅检查媒体类型。

    年份过滤统一推迟到搜索后（`year_filter_reason`），基于 TMDB 准确数据判断。

    Returns:
        (通过, 原因字符串)
    """
    prefix = f"{src_name}_"
    media_type = cfg.get(f"{prefix}media_type", "all")
    if media_type and media_type != "all" and item.type_hint and item.type_hint != media_type:
        return False, f"{SOURCE_NAMES.get(src_name, src_name)} 媒体类型过滤: 配置={media_type}, 条目={item.type_hint}"

    # 年份过滤统一推迟到搜索后，基于 TMDB 准确数据判断
    return True, ""


def vote_filter_reason(cfg: dict, src_name: str, vote: float) -> str | None:
    """评分过滤（全局 + 每源，取较高者）。

    Returns:
        过滤原因字符串；通过时返回 None
    """
    min_vote = cfg.get("min_vote", 0) or 0
    src_min_vote = cfg.get(f"{src_name}_min_vote", 0) or 0
    effective = max(min_vote, src_min_vote)
    if effective > 0 and (vote < effective or vote == 0):
        return f"评分过滤: {vote} < {effective}"
    return None


async def year_filter_reason(
    cfg: dict,
    src_name: str,
    year: str | int | None,
    media_type: str,
    tmdb_id: int,
    title: str,
    tmdb_service: TMDBService | None,
) -> str | None:
    """最小年份过滤（全局 + 每源，取较高者；基于 TMDB 搜索结果年份）。

    多季电视剧：最新季满足最小年份则放行。

    Returns:
        过滤原因字符串；通过时返回 None
    """
    min_year = cfg.get("min_year", 0) or 0
    src_min_year = cfg.get(f"{src_name}_min_year", 0) or 0
    effective = max(min_year, src_min_year)
    if not (effective > 0 and year):
        return None

    try:
        item_year_int = int(str(year)[:4])
    except (ValueError, TypeError):
        return None
    if item_year_int >= effective:
        return None

    # 多季电视剧：最新季满足最小年份则放行
    if media_type == "tv" and tmdb_service:
        detail = await tmdb_service.get_tv_detail(tmdb_id)
        last_air = str(detail.get("last_air_date") or "")[:4]
        if last_air.isdigit() and int(last_air) >= effective:
            logger.info(
                f"[自动订阅] 多季剧最新季满足年份: {title} "
                f"(首播={item_year_int}, 最新季={last_air}, min_year={effective})"
            )
            return None
        return f"最小年份过滤: 首播={item_year_int}, 最新季={last_air} < {effective}"

    return f"最小年份过滤: {item_year_int} < {effective}"
