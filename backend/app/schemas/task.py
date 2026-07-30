"""定时任务 Pydantic schemas。"""

from pydantic import BaseModel, Field


class TaskConfigUpdate(BaseModel):
    """定时任务配置更新请求。"""

    interval_minutes: int | None = Field(None, ge=5, le=1440, description="全量扫描间隔（分钟）")
    light_interval_minutes: int | None = Field(None, ge=1, le=120, description="轻量刷新间隔（分钟）")
    sync_interval_minutes: int | None = Field(None, ge=5, le=1440, description="NF 订阅同步间隔（分钟）")
    tmdb_interval_minutes: int | None = Field(None, ge=5, le=1440, description="TMDB 增量刷新间隔（分钟）")
    mp_supplement_enabled: bool | None = Field(None, description="是否启用 MP 补充搜索")
    auto_sync_enabled: bool | None = Field(None, description="是否启用自动同步")


class TaskStatusResponse(BaseModel):
    """定时任务状态响应。"""

    running: bool
    last_run: str | None = None
    last_result: dict | None = None
    config: dict


class TaskTriggerResponse(BaseModel):
    """手动触发任务响应。"""

    success: bool
    message: str
    sync_count: int = 0
    mp_search_count: int = 0
