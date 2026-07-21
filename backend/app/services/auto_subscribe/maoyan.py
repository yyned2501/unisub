"""自动订阅 — 猫眼榜单源（票房 + 网播热度）。"""

import random
import re
from datetime import date, timedelta

import httpx

from app.core.logger import init_logger
from app.services.auto_subscribe.models import RankMediaItem

logger = init_logger(__name__)

MAOYAN_URL = "https://piaofang.maoyan.com"
REQUEST_TIMEOUT = 30

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edge/120.0.0.0",
]

# 猫眼 API 内部编码（参考原插件）
# seriesType: "0"=电视剧, "1"=网络剧, "2"=综艺, "4"=电视剧+网络剧
SERIES_CODE = {"tv": "0", "web": "1", "variety": "2", "series": "4"}
# platformType: ""=全网, "3"=腾讯视频, "2"=爱奇艺, "7"=芒果TV, "1"=优酷, "5"=搜狐, "4"=乐视, "6"=PPTV
PLATFORM_CODE = {
    "腾讯视频": "3",
    "爱奇艺": "2",
    "芒果TV": "7",
    "优酷": "1",
    "搜狐视频": "5",
    "乐视": "4",
    "PP视频": "6",
}
# 前端配置值 → 系列类型码映射
WEB_TYPE_TO_SERIES_CODE = {"tv": "0", "动漫": "4"}


async def fetch(options: dict) -> list[RankMediaItem]:
    """抓取猫眼榜单。

    Args:
        options: 配置字典

    Returns:
        RankMediaItem 列表
    """
    items: list[RankMediaItem] = []

    if options.get("maoyan_movie_box", True):
        try:
            box_items = await _fetch_movie_box()
            items.extend(box_items)
        except Exception as e:
            logger.warning(f"[猫眼] 票房榜抓取失败: {e}")

    platforms = options.get("maoyan_web_platforms", [])
    media_types = options.get("maoyan_web_types", [])
    num = options.get("maoyan_num", 10)

    if platforms and media_types:
        try:
            web_items = await _fetch_web_heat(platforms, media_types, num)
            items.extend(web_items)
        except Exception as e:
            logger.warning(f"[猫眼] 热度榜抓取失败: {e}")

    return items


async def _fetch_movie_box() -> list[RankMediaItem]:
    """抓取实时票房榜（JSON API）。"""
    headers = _headers()
    data = await _fetch_json(f"{MAOYAN_URL}/dashboard-ajax/movie", headers=headers)
    if not data:
        return []

    movie_list = (data.get("movieList") or {}).get("list") or []
    items: list[RankMediaItem] = []
    for entry in movie_list:
        info = entry.get("movieInfo") or {}
        name = (info.get("movieName") or "").strip()
        if not name:
            continue
        year = _year_from_release_info(info.get("releaseInfo"))
        items.append(
            RankMediaItem(
                title=name,
                year=year,
                type_hint="movie",
                source_meta={"source": "maoyan", "type": "movie_box"},
                unique_seed=f"maoyan:box:{name}",
            )
        )
    return items


async def _fetch_web_heat(
    platforms: list[str],
    media_types: list[str],
    num: int,
) -> list[RankMediaItem]:
    """抓取网播热度数据。"""
    headers = _headers()
    items: list[RankMediaItem] = []
    seen: set[str] = set()

    for platform in platforms:
        platform_code = PLATFORM_CODE.get(platform)
        if platform_code is None:
            continue
        for media_type in media_types:
            series_code = WEB_TYPE_TO_SERIES_CODE.get(media_type)
            if series_code is None:
                continue
            try:
                batch = await _fetch_web_heat_one(series_code, platform_code, num, headers)
                for item in batch:
                    key = item.unique_seed or item.title
                    if key not in seen:
                        seen.add(key)
                        items.append(item)
            except Exception as e:
                logger.debug(f"[猫眼] 热度抓取失败: {platform}/{media_type}: {e}")

    return items


async def _fetch_web_heat_one(
    series_code: str,
    platform_code: str,
    num: int,
    headers: dict,
) -> list[RankMediaItem]:
    """抓取单平台单类型的网播热度。"""
    url = f"{MAOYAN_URL}/dashboard/webHeatData"
    params = {"seriesType": series_code, "platformType": platform_code, "showDate": "2"}
    data = await _fetch_json(url, headers=headers, params=params)
    if not data:
        return []

    items: list[RankMediaItem] = []
    raw_list = (data.get("dataList") or {}).get("list") or []
    for entry in raw_list[:num]:
        info = entry.get("seriesInfo") or {}
        name = (info.get("name") or "").strip()
        if not name:
            continue
        year = _year_from_release_info(info.get("releaseInfo"))
        type_hint = "tv" if series_code in ("0", "1", "4") else "movie"
        items.append(
            RankMediaItem(
                title=name,
                year=year,
                type_hint=type_hint,
                source_meta={"source": "maoyan", "type": "web_heat"},
                unique_seed=f"maoyan:web:{name}",
            )
        )
    return items


def _headers() -> dict:
    """构建请求头。"""
    return {
        "user-agent": random.choice(_USER_AGENTS),
        "accept": "text/html,application/json,*/*",
        "referer": MAOYAN_URL,
    }


async def _fetch_json(
    url: str,
    headers: dict | None = None,
    params: dict | None = None,
) -> dict | list | None:
    """用 httpx GET 请求 JSON 数据。"""
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.debug(f"[猫眼] 请求失败 {url[:60]}: {e}")
        return None


def _year_from_release_info(release_info: str | None) -> str | None:
    """由 releaseInfo（如"上映11天"）反推年份。"""
    if not release_info:
        return None
    days = re.findall(r"\d+", release_info)
    if not days:
        return None
    try:
        target = date.today() - timedelta(days=int(days[0]))
        return str(target.year)
    except (ValueError, OverflowError):
        return None
