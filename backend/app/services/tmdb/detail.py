"""TMDB 详情纯计算函数 — 已播集数、按季已播、下一集播出日期。

从 tmdb.py 拆出：基于 /tv/{id} 详情字典的纯计算，不发请求、无外部依赖，
供已持有 detail 的调用方复用，避免对同一端点重复请求。
"""

from __future__ import annotations

from datetime import UTC, date, datetime


def aired_from_detail(detail: dict) -> int | None:
    """从已获取的剧集详情计算实际已播出集数（纯计算，不发请求）。

    对连载中的剧集（Returning Series），根据 last_episode_to_air
    累加已完成季的全集数 + 当前季已播集数；已完结/单次剧集返回 None
    表示使用 TMDB 总量即可。

    Args:
        detail: /tv/{id} 返回的详情字典

    Returns:
        已播出的集数，或 None（已完结/数据不足）
    """
    status = detail.get("status", "")
    if status != "Returning Series":
        return None  # 已完结的剧集直接用 TMDB 总量

    # 获取最后一集播出信息
    last = detail.get("last_episode_to_air")
    if not last:
        return None

    last_season = last.get("season_number", 0)
    last_episode = last.get("episode_number", 0)
    if last_season == 0 or last_episode == 0:
        return None

    # 累加已完结季的全集数
    total = 0
    seasons = detail.get("seasons", [])
    for s in seasons:
        sn = s.get("season_number", 0)
        if sn == 0:
            continue  # 跳过特典季
        ec = s.get("episode_count", 0) or 0
        if sn < last_season:
            total += ec

    total += last_episode
    return total


def aired_count_by_season(detail: dict) -> dict[int, int]:
    """从剧集详情计算每季已播出集数 ``{季号: 已播集数}``（纯计算，不发请求）。

    用于过滤 TMDB 脏数据：announced 但未开播的季会带 episode_count（计划总集数），
    若据此订阅会让 MP 去追根本不存在的集。此函数算出每季真实已播集数，
    已播为 0 的季不应被 MP 订阅。

    判定规则：
        - 季首播日 air_date 缺失或晚于今天 → 0（未开播）
        - 连载剧（Returning Series）：早于当前播出季的视为全部播出（=总集数）；
          当前季用 last_episode_to_air 的集号；晚于当前季的为 0
        - 其他状态（已完结/取消等）且已开播 → 视为全部播出（=总集数）

    Args:
        detail: /tv/{id} 返回的详情字典（含 seasons / status / last_episode_to_air）

    Returns:
        ``{季号: 已播集数}``，不含特典季（season_number=0）
    """
    today = datetime.now(UTC).date()
    status = detail.get("status", "")
    last = detail.get("last_episode_to_air") or {}
    last_season = last.get("season_number") or 0
    last_episode = last.get("episode_number") or 0

    result: dict[int, int] = {}
    for s in detail.get("seasons") or []:
        sn = s.get("season_number")
        if sn is None or sn == 0:
            continue  # 跳过特典季
        episode_count = s.get("episode_count") or 0
        air_date = parse_date(s.get("air_date"))
        if air_date is None:
            # 无首播日：若季号早于当前播出季，视为已全部播出
            # TMDB 对连载老剧的早期季可能不设 air_date，但实际已播完
            if status == "Returning Series" and sn < last_season:
                result[sn] = episode_count
            else:
                result[sn] = 0
            continue
        if air_date > today:
            result[sn] = 0  # 首播日在未来 → 未开播
            continue
        if status == "Returning Series":
            if sn < last_season:
                result[sn] = episode_count  # 早于当前季 → 已全部播出
            elif sn == last_season:
                result[sn] = last_episode  # 当前季 → 已播到 last_episode
            else:
                result[sn] = 0  # 晚于当前播出季 → 未播
        else:
            result[sn] = episode_count  # 已完结/取消等：已开播即视为全部播出
    return result


def next_air_date_from_detail(detail: dict) -> str | None:
    """从已获取的剧集详情提取下一集播出日期（纯计算，不发请求）。

    Args:
        detail: /tv/{id} 返回的详情字典

    Returns:
        播出日期字符串（YYYY-MM-DD）或 None（已完结/无下一集）
    """
    next_ep = detail.get("next_episode_to_air")
    if next_ep:
        return next_ep.get("air_date")
    return None


def parse_date(value: str | None) -> date | None:
    """把 ``YYYY-MM-DD`` 字符串解析为 date，缺失或非法格式返回 None。

    Args:
        value: 日期字符串（TMDB 的 air_date 等，可能带时间后缀）

    Returns:
        解析出的 date，或 None
    """
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
