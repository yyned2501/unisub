"""自动订阅 — 数据模型与常量。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RankMediaItem:
    """榜单抓取阶段产出的标准化中间条目。"""

    title: str
    year: str | None = None
    type_hint: str | None = None  # "movie" | "tv" | None
    season: int | None = None
    douban_id: str | None = None
    bangumi_id: int | None = None
    poster: str | None = None
    source_meta: dict = field(default_factory=dict)
    unique_seed: str = ""

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 安全 dict（供持久化）。"""
        return {
            "title": self.title,
            "year": self.year,
            "type_hint": self.type_hint,
            "season": self.season,
            "douban_id": self.douban_id,
            "bangumi_id": self.bangumi_id,
            "poster": self.poster,
            "source_meta": dict(self.source_meta),
            "unique_seed": self.unique_seed,
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> RankMediaItem:
        """从持久化 dict 还原；缺字段走 dataclass 安全默认。"""
        d = d or {}
        return cls(
            title=d.get("title", ""),
            year=d.get("year"),
            type_hint=d.get("type_hint"),
            season=d.get("season"),
            douban_id=d.get("douban_id"),
            bangumi_id=d.get("bangumi_id"),
            poster=d.get("poster"),
            source_meta=d.get("source_meta") or {},
            unique_seed=d.get("unique_seed", ""),
        )


# 最终处理状态
STATUS_SUBSCRIBED = "subscribed"  # 新增订阅成功
STATUS_SUBSCRIBED_EXISTS = "exists"  # 已订阅（跳过）
STATUS_EXISTS = STATUS_SUBSCRIBED_EXISTS  # 别名，兼容旧用法
STATUS_IN_LIBRARY = "in_library"  # 媒体库已存在（跳过）
STATUS_UNRECOGNIZED = "unrecognized"  # NextFind 搜不到
STATUS_FILTERED = "filtered"  # 被过滤
STATUS_ALREADY = "already_handled"  # 历史已处理（跳过）
STATUS_ERROR = "error"  # 异常

STATUS_LABELS = {
    STATUS_SUBSCRIBED: "新增订阅",
    STATUS_SUBSCRIBED_EXISTS: "已订阅",
    STATUS_IN_LIBRARY: "库中已有",
    STATUS_UNRECOGNIZED: "未识别",
    STATUS_FILTERED: "已过滤",
    STATUS_ALREADY: "已处理",
    STATUS_ERROR: "失败",
}

# 视为「正向终态」——记入历史、后续跑不再重复处理。
TERMINAL_STATUSES = (STATUS_SUBSCRIBED, STATUS_SUBSCRIBED_EXISTS, STATUS_IN_LIBRARY)


def make_history_key(tmdb_id: int, media_type: str, season: int | None = None) -> str:
    """生成跨轮去重的历史键：电影按 tmdb，剧集按 tmdb+季。"""
    if str(media_type).lower() == "tv":
        return f"tv:{tmdb_id}:s{season}" if season is not None else f"tv:{tmdb_id}"
    return f"movie:{tmdb_id}"


@dataclass
class Filters:
    """全局过滤阈值（0 = 不启用）。"""

    min_year: int = 0
    min_vote: float = 0.0
    min_popularity: int = 0
    media_type: str = "all"  # all | movie | tv


@dataclass
class RunResult:
    """一轮运行的汇总结果。"""

    stats: dict[str, dict[str, int]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    added: list[dict] = field(default_factory=list)
    handled: dict[str, dict] = field(default_factory=dict)
    nf_cache: dict = field(default_factory=dict)
    auth_error: str = ""


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
    "douban_rsshub": "https://rsshub.app",
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
    "proxy_url": "",
}

SOURCE_NAMES = {
    "douban": "豆瓣榜单",
    "mikan": "Mikan 新番",
    "maoyan": "猫眼榜单",
}
