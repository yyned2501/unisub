"""Emby 媒体库分析 Schemas。"""

from datetime import datetime

from pydantic import BaseModel, Field


class EmbySeriesStatus(BaseModel):
    """单部剧集在 Emby 中的存在状态。"""

    tmdb_id: int
    title: str | None = None
    year: int | None = None
    poster_url: str | None = None
    in_emby: bool = False
    emby_id: str | None = None
    emby_path: str | None = None
    present_episodes: int | None = None
    missing_eps_count: int = 0
    overview: str | None = None
    tmdb_aired_eps: int | None = None
    tmdb_total_eps: int | None = None
    adjusted_missing: int | None = None
    emby_image_url: str | None = None
    is_subscribed: bool = False
    is_blacklisted: bool = False
    emby_name: str | None = None
    emby_year: int | None = None
    emby_episode_count: int | None = None


class EmbyLibraryAnalysis(BaseModel):
    """Emby 媒体库完整性分析结果。"""

    total_series: int = 0
    subscribed_count: int = 0
    blacklisted_count: int = 0
    series: list[EmbySeriesStatus] = Field(default_factory=list)


class EmbyBlacklistEntry(BaseModel):
    """黑名单条目。"""

    tmdb_id: int
    created_at: datetime


class BlacklistCreate(BaseModel):
    """添加黑名单请求。"""

    tmdb_id: int


class BlacklistActionResponse(BaseModel):
    """黑名单操作响应。"""

    success: bool = True
    message: str = ""


class EmbySubscribeRequest(BaseModel):
    """从 Emby 缺集分析发起订阅的请求。"""

    tmdb_id: int
    title: str
    media_type: str = "tv"
    poster_url: str | None = None
    year: int | None = None


class EmbyActionRequest(BaseModel):
    """Emby 通用操作请求（仅需 tmdb_id）。"""

    tmdb_id: int


class EmbyActionResponse(BaseModel):
    """Emby 操作结果响应。"""

    success: bool = True
    message: str = ""
