"""CloudDrive2 配置 Pydantic schemas。"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import MaskedApiKeyMixin


class Cd2ConfigUpdate(BaseModel):
    """更新 CloudDrive2 配置的请求体。"""

    base_url: str = Field(..., description="CloudDrive2 gRPC-Web 地址")
    api_key: str = Field(..., description="CloudDrive2 API Key")
    target_path: str = Field(..., description="无效媒体目录的移动目标位置")
    path_prefix: str = Field("", description="Emby 路径前缀（如 /media/Symedia）")
    path_replacement: str = Field("", description="替换为 CD2 路径（如 /115open/已整理）")
    enabled: bool = Field(True, description="是否启用")


class Cd2ConfigResponse(MaskedApiKeyMixin, BaseModel):
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


class Cd2TestResult(BaseModel):
    """CloudDrive2 连接测试结果。"""

    success: bool
    message: str
    details: dict[str, str | bool] | None = None
