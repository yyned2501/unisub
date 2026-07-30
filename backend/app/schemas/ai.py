"""AI 配置 Pydantic schemas。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AiConfigResponse(BaseModel):
    """AI 配置响应。"""

    config: dict[str, Any] = Field(default_factory=dict)


class AiConfigUpdate(BaseModel):
    """AI 配置更新请求。"""

    config: dict[str, Any] = Field(default_factory=dict)


class AiModelListRequest(BaseModel):
    """AI 模型列表请求。"""

    api_base: str = Field(default="", description="兼容 OpenAI 的 API 地址")
    api_key: str = Field(default="", description="API Key")

    @property
    def effective_api_base(self) -> str:
        """返回移除末尾斜杠后的 API 地址。"""
        return self.api_base.rstrip("/")


class AiModelItem(BaseModel):
    """单个 AI 模型信息。"""

    id: str
    object: str = "model"


class AiModelListResponse(BaseModel):
    """AI 模型列表响应。"""

    models: list[AiModelItem] = Field(default_factory=list)
