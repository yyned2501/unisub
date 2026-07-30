"""AI 配置路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
from app.schemas.ai import AiConfigResponse, AiConfigUpdate, AiModelListRequest, AiModelListResponse
from app.services.ai_config import fetch_ai_models, get_ai_config_store

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
async def list_ai_models(body: AiModelListRequest) -> AiModelListResponse:
    """获取兼容 OpenAI API 提供的模型列表。"""
    base = body.effective_api_base
    if not base or not body.api_key:
        raise HTTPException(status_code=422, detail="API 地址和 API Key 不能为空")

    try:
        models = await fetch_ai_models(base, body.api_key)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return AiModelListResponse(models=models)
