"""自动订阅 — 数据模型与常量。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RankMediaItem:
    """榜单抓取阶段产出的标准化中间条目。"""

    title: str
    year: str | None = None
    type_hint: str | None = None  # "movie" | "tv" | None
    season: int | None = None
    poster: str | None = None
    source_meta: dict = field(default_factory=dict)
    unique_seed: str = ""


# 最终处理状态
STATUS_SUBSCRIBED = "subscribed"  # 新增订阅成功
STATUS_EXISTS = "exists"  # 已订阅（跳过）
STATUS_IN_LIBRARY = "in_library"  # 媒体库已存在（跳过）
STATUS_UNRECOGNIZED = "unrecognized"  # NextFind 搜不到
STATUS_FILTERED = "filtered"  # 被过滤
STATUS_ALREADY = "already_handled"  # 历史已处理（跳过）
STATUS_ERROR = "error"  # 异常

STATUS_LABELS = {
    STATUS_SUBSCRIBED: "新增订阅",
    STATUS_EXISTS: "已订阅",
    STATUS_IN_LIBRARY: "库中已有",
    STATUS_UNRECOGNIZED: "未识别",
    STATUS_FILTERED: "已过滤",
    STATUS_ALREADY: "已处理",
    STATUS_ERROR: "失败",
}

# 默认配置
DEFAULT_CONFIG = {
    # 全局过滤
    "min_year": 0,
    "min_vote": 0,
    "min_popularity": 0,
    "media_type": "all",
    # 定时
    "enabled": False,
    "schedule_cron": "0 8 * * *",
    # 豆瓣
    "douban_enabled": False,
    "douban_ranks": ["movie-hot-gaia", "tv-hot"],
    "douban_rsshub": "https://rss.awdys.cn",
    "douban_rss_custom": "",
    "douban_min_year": 0,
    "douban_min_vote": 0,
    "douban_media_type": "all",
    # Mikan
    "mikan_enabled": False,
    "mikan_season": "当前",
    "mikan_year": 0,
    "mikan_resolve_detail": True,
    "mikan_min_year": 0,
    "mikan_min_vote": 0,
    # 猫眼
    "maoyan_enabled": False,
    "maoyan_movie_box": True,
    "maoyan_web_platforms": [],
    "maoyan_web_types": [],
    "maoyan_num": 10,
    "maoyan_min_year": 0,
    "maoyan_min_vote": 0,
    "maoyan_media_type": "all",
}

SOURCE_NAMES = {
    "douban": "豆瓣榜单",
    "mikan": "Mikan 新番",
    "maoyan": "猫眼榜单",
}
