"""订阅 Pydantic schemas。"""

from datetime import datetime

from pydantic import BaseModel, Field


class SubscriptionCreate(BaseModel):
    """创建订阅的请求体。"""

    tmdb_id: int = Field(..., description="TMDB ID")
    media_type: str = Field(..., description="媒体类型（movie / tv）")
    title: str = Field(..., description="媒体标题")
    poster_url: str | None = Field(None, description="海报 URL")
    year: int | None = Field(None, description="发行年份")


class SubscriptionResponse(BaseModel):
    """订阅记录的响应体。"""

    id: str
    tmdb_id: int
    media_type: str
    title: str
    poster_url: str | None = None
    year: int | None = None
    nf_subscribed: bool = False
    nf_status: str | None = None
    nf_missing_eps: int = 0
    nf_sub_id: str | None = None
    completed: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SubscriptionSyncResult(BaseModel):
    """单条订阅同步结果。"""

    tmdb_id: int
    title: str
    action: str = "skipped"  # created / pushed_to_nf / updated / skipped
    nf_status: str | None = None
    nf_missing_eps: int = 0
    nf_subscribed: bool = False
    needs_mp_search: bool = False
    message: str = ""
