"""自动订阅 Pydantic schemas。"""

from pydantic import BaseModel, Field


class AutoSubConfigResponse(BaseModel):
    """自动订阅配置响应。"""

    config: dict = Field(default_factory=dict)
    last_run: str | None = None
    last_stats: dict | None = None
    enabled_sources: list[str] = Field(default_factory=list)
    status_labels: dict = Field(default_factory=dict)
    source_names: dict = Field(default_factory=dict)
    running: bool = False
    last_error: str | None = None


class AutoSubConfigUpdate(BaseModel):
    """自动订阅配置更新请求。"""

    config: dict = Field(default_factory=dict)


class AutoSubRunResponse(BaseModel):
    """手动触发运行响应。"""

    success: bool = True
    started: bool = True
    message: str = ""


class AutoSubHistoryItem(BaseModel):
    """单条自动订阅历史记录。"""

    key: str
    status: str
    time: str | None = None
    tmdb_id: int | None = None
    media_type: str | None = None


class AutoSubHistoryResponse(BaseModel):
    """自动订阅历史响应。"""

    items: list[AutoSubHistoryItem] = Field(default_factory=list)
    last_run: str | None = None
    stats: dict | None = None


class AutoSubMetaResponse(BaseModel):
    """自动订阅元数据响应（供前端下拉选项）。"""

    douban_ranks: list[dict] = Field(default_factory=list)
    maoyan_platforms: list[dict] = Field(default_factory=list)
    maoyan_media_types: list[dict] = Field(default_factory=list)
    seasons: list[dict] = Field(default_factory=list)
    source_names: dict = Field(default_factory=dict)
    status_labels: dict = Field(default_factory=dict)
