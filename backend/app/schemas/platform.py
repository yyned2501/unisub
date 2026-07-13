"""平台配置 Pydantic schemas。"""

from datetime import datetime

from pydantic import BaseModel, Field


class PlatformConfigCreate(BaseModel):
    """创建平台配置的请求体。"""

    name: str = Field(..., description="平台名称（nextfind / moviepilot）")
    base_url: str = Field(..., description="API 基础地址")
    api_key: str = Field(..., description="鉴权密钥")
    enabled: bool = Field(True, description="是否启用")


class PlatformConfigUpdate(BaseModel):
    """更新平台配置的请求体，所有字段可选，仅更新传入的字段。"""

    name: str | None = Field(None, description="平台名称")
    base_url: str | None = Field(None, description="API 基础地址")
    api_key: str | None = Field(None, description="鉴权密钥")
    enabled: bool | None = Field(None, description="是否启用")


class PlatformConfigResponse(BaseModel):
    """平台配置的响应体。"""

    id: str
    name: str
    base_url: str
    api_key: str
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PlatformTestResult(BaseModel):
    """平台连接测试结果。"""

    success: bool
    message: str
    details: dict | None = None
