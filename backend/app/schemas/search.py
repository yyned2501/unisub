"""搜索 Pydantic schemas。"""

from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    """搜索查询参数。"""

    q: str = Field(..., description="搜索关键词")
    type: str = Field("all", description="媒体类型（movie / tv / all）")


class SearchResultItem(BaseModel):
    """搜索结果中的单个媒体条目。"""

    tmdb_id: int
    title: str
    media_type: str
    year: int | None = None
    poster_url: str | None = None
    overview: str | None = None
    is_subscribed: bool = False


class SearchResponse(BaseModel):
    """搜索响应体。"""

    total: int
    items: list[SearchResultItem]
