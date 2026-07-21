"""看板 Pydantic schemas。"""

from datetime import datetime

from pydantic import BaseModel


class DashboardStats(BaseModel):
    """看板统计数据。"""

    total_subscriptions: int = 0
    movie_count: int = 0
    tv_count: int = 0
    missing_count: int = 0
    completed_count: int = 0
    tmdb_cached_total: int = 0
    tmdb_data_filled: int = 0


class PlatformStatus(BaseModel):
    """单个平台的连接状态。"""

    name: str
    enabled: bool
    connected: bool
    message: str


class ActivityLogResponse(BaseModel):
    """活动日志响应体。"""

    id: str
    action: str
    tmdb_id: int | None = None
    message: str
    created_at: datetime

    model_config = {"from_attributes": True}


class NextFindQuota(BaseModel):
    """NextFind 额度/积分信息。"""

    quota: dict | None = None
    error: str | None = None
