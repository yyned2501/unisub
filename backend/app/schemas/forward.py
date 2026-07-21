"""Forward API Pydantic schemas — 极简字段结构，对齐 forward app 期望。"""

from pydantic import BaseModel, Field


class ForwardSubscribeItem(BaseModel):
    """订阅列表项 — 极简字段，对齐 forward app 期望。"""

    id: int = Field(..., description="TMDB ID")
    tmdbid: int = Field(..., description="TMDB ID")
    name: str | None = Field(None, description="媒体标题")
    type: str = Field(..., description="媒体类型: 电影 / 电视剧")


class ForwardTVSubscribeItem(ForwardSubscribeItem):
    """剧集订阅 — 含缺集信息。"""

    total_episode: int | None = Field(None, description="总集数")
    lack_episode: int | None = Field(None, description="缺集数")
    completed_episode: int | None = Field(None, description="已入库集数")


class ForwardSearchItem(BaseModel):
    """搜索结果项。"""

    title: str | None = Field(None, description="标题")
    en_title: str | None = Field(None, description="英文标题")
    year: str | None = Field(None, description="年份")
    type: str | None = Field(None, description="媒体类型")
    season: int | None = Field(None, description="季号")
    tmdb_id: int | None = Field(None, description="TMDB ID")
    imdb_id: str | None = Field(None, description="IMDB ID")
    douban_id: str | None = Field(None, description="豆瓣 ID")
    overview: str | None = Field(None, description="简介")
    vote_average: float = Field(0.0, description="评分")
    poster_path: str | None = Field(None, description="海报 URL")
    detail_link: str | None = Field(None, description="详情链接")


class ForwardLoginResponse(BaseModel):
    """登录响应 — 对齐 forward app 期望格式。"""

    access_token: str = Field(..., description="JWT token")
    token_type: str = Field("bearer", description="Token 类型")
    super_user: bool = Field(True, description="是否超级用户")
    user_id: int = Field(1, description="用户 ID")
    user_name: str = Field("", description="用户名")
    avatar: str = Field("", description="头像 URL")


class ForwardSubscribeInput(BaseModel):
    """添加订阅请求体。"""

    tmdbid: int | None = Field(None, description="TMDB ID")
    name: str | None = Field(None, description="媒体标题")
    type: str | None = Field(None, description="媒体类型: movie / tv")
    mediaid: str | None = Field(None, description="媒体 ID（如 tmdb:123）")


class ForwardActionResponse(BaseModel):
    """操作响应。"""

    success: bool = Field(True, description="是否成功")
    message: str = Field("success", description="消息")
    data: dict = Field(default_factory=dict, description="数据")
