"""Emby 媒体库分析 Schemas。"""

from datetime import datetime

from pydantic import BaseModel


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


class EmbyActionResponse(BaseModel):
    """Emby 操作结果响应。"""

    success: bool = True
    message: str = ""
