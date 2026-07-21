"""CloudDrive2 配置 Pydantic schemas。"""

from datetime import datetime

from pydantic import BaseModel, Field, field_serializer


def _mask_api_key(key: str) -> str:
    """脱敏 API Key，只保留前 4 位和后 4 位，中间用 **** 替代。"""
    if not key or len(key) <= 8:
        return "****"
    return f"{key[:4]}****{key[-4:]}"


class Cd2ConfigUpdate(BaseModel):
    """更新 CloudDrive2 配置的请求体。"""

    base_url: str = Field(..., description="CloudDrive2 gRPC-Web 地址")
    api_key: str = Field(..., description="CloudDrive2 API Key")
    target_path: str = Field(..., description="无效媒体目录的移动目标位置")
    path_prefix: str = Field("", description="Emby 路径前缀（如 /media/Symedia）")
    path_replacement: str = Field("", description="替换为 CD2 路径（如 /115open/已整理）")
    enabled: bool = Field(True, description="是否启用")


class Cd2ConfigResponse(BaseModel):
    """CloudDrive2 配置响应体（api_key 自动脱敏）。"""

    id: str
    base_url: str
    api_key: str
    target_path: str
    path_prefix: str = ""
    path_replacement: str = ""
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("api_key")
    def mask_api_key(self, value: str) -> str:
        return _mask_api_key(value)


class Cd2TestResult(BaseModel):
    """CloudDrive2 连接测试结果。"""

    success: bool
    message: str
    details: dict[str, str | bool] | None = None
