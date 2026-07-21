"""Emby 媒体库缓存 Pydantic schemas。"""

from pydantic import BaseModel, Field


class EmbyCacheResponse(BaseModel):
    """Emby 缓存剧集的响应体，含 adjusted_missing 计算字段。"""

    tmdb_id: int
    emby_series_name: str | None = None
    emby_year: int | None = None
    emby_episode_count: int | None = None
    emby_image_url: str | None = None
    emby_path: str | None = None
    emby_library_name: str | None = None
    overview: str | None = None
    poster_url: str | None = None
    tmdb_total_eps: int | None = None
    tmdb_aired_eps: int | None = None
    tmdb_next_air_date: str | None = None
    is_subscribed: bool = False
    is_blacklisted: bool = False
    adjusted_missing: int | None = None

    model_config = {"from_attributes": True}


class Tmdb404Item(BaseModel):
    """TMDB 404 条目 — EmbyCache 有但 TmdbCache 无对应记录。"""

    tmdb_id: int
    emby_series_name: str | None = None
    emby_year: int | None = None
    emby_path: str | None = None
    cd2_path: str | None = None
    emby_image_url: str | None = None
    detected_at: str | None = None


class EmbySyncResult(BaseModel):
    """Emby 同步操作结果。"""

    success: bool = True
    total_synced: int = 0
    message: str = ""


class EmbyMissingAnalysis(BaseModel):
    """缺集分析结果 — 只展示有缺集的剧集。"""

    total_series: int = 0
    subscribed_count: int = 0
    missing_count: int = 0
    series: list[EmbyCacheResponse] = Field(default_factory=list)
    page: int = 1
    page_size: int = 50
    total_pages: int = 1
    libraries: list[str] = Field(default_factory=list, description="所有 Emby 媒体库名称列表")
