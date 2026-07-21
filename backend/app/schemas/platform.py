"""平台配置 Pydantic schemas。"""

from datetime import datetime

from pydantic import BaseModel, Field, field_serializer


def _mask_api_key(key: str) -> str:
    """脱敏 API Key，只保留前 4 位和后 4 位，中间用 **** 替代。"""
    if not key or len(key) <= 8:
        return "****"
    return f"{key[:4]}****{key[-4:]}"


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
    """平台配置的响应体（api_key 自动脱敏）。"""

    id: str
    name: str
    base_url: str
    api_key: str
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("api_key")
    def mask_api_key(self, value: str) -> str:
        return _mask_api_key(value)


class PlatformTestResult(BaseModel):
    """平台连接测试结果。"""

    success: bool
    message: str
    details: dict | None = None
