"""AI 配置路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
from app.core.http_client import http_client
from app.schemas.ai import AiConfigResponse, AiConfigUpdate, AiModelListRequest, AiModelListResponse
from app.services.ai_config import get_ai_config_store

router = APIRouter(prefix="/api/ai", tags=["AI 配置"], dependencies=[Depends(get_current_user)])


@router.get("/config", response_model=AiConfigResponse)
async def get_ai_config() -> AiConfigResponse:
    """获取独立 AI 配置。"""
    return AiConfigResponse(config=get_ai_config_store().load_config())


@router.put("/config", response_model=AiConfigResponse)
async def update_ai_config(body: AiConfigUpdate) -> AiConfigResponse:
    """保存独立 AI 配置。"""
    return AiConfigResponse(config=get_ai_config_store().save_config(body.config))


@router.post("/models", response_model=AiModelListResponse)
async def fetch_ai_models(body: AiModelListRequest) -> AiModelListResponse:
    """获取兼容 OpenAI API 提供的模型列表。"""
    base = body.effective_api_base
    if not base or not body.api_key:
        raise HTTPException(status_code=422, detail="API 地址和 API Key 不能为空")

    url = f"{base}/v1/models"
    headers = {"Authorization": f"Bearer {body.api_key}"}
    data: dict[str, Any] = await http_client.get(url, headers=headers)
    if "error" in data:
        raise HTTPException(status_code=502, detail="获取 AI 模型列表失败")

    models = data.get("data", [])
    return AiModelListResponse(
        models=[
            {"id": item["id"], "object": item.get("object", "model")}
            for item in models
            if isinstance(item, dict) and item.get("id")
        ]
    )
