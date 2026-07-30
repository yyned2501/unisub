"""平台配置路由 — 完整 CRUD 与连接测试。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.logger import init_logger
from app.models.platform_config import PlatformConfig
from app.schemas.platform import (
    PlatformConfigCreate,
    PlatformConfigResponse,
    PlatformConfigUpdate,
    PlatformTestResult,
)
from app.services import invalidate_platform_cache
from app.services.platform import (
    create_platform,
    delete_platform,
    list_platforms,
    test_platform_connection,
    update_platform,
)

router = APIRouter(prefix="/api/platforms", tags=["平台配置"], dependencies=[Depends(get_current_user)])
logger = init_logger()


@router.get("", response_model=list[PlatformConfigResponse])
async def list_platforms_endpoint(db: AsyncSession = Depends(get_db)):
    """获取所有平台配置列表。"""
    return await list_platforms(db)


@router.post("", response_model=PlatformConfigResponse, status_code=201)
async def create_platform_endpoint(body: PlatformConfigCreate, db: AsyncSession = Depends(get_db)):
    """添加新的平台配置。

    平台名称必须唯一（nextfind / moviepilot）。
    """
    try:
        config = await create_platform(
            db,
            name=body.name,
            base_url=body.base_url,
            api_key=body.api_key,
            enabled=body.enabled,
        )
        invalidate_platform_cache(body.name)
        logger.info("平台配置已创建: %s", body.name)
        return config
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put("/{platform_id}", response_model=PlatformConfigResponse)
async def update_platform_endpoint(
    platform_id: str,
    body: PlatformConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新平台配置，仅更新传入的字段。"""
    update_data = body.model_dump(exclude_unset=True)
    config = await update_platform(db, platform_id, update_data)
    if not config:
        raise HTTPException(status_code=404, detail="平台配置不存在")
    invalidate_platform_cache(config.name)
    logger.info("平台配置已更新: %s", config.name)
    return config


@router.delete("/{platform_id}", status_code=204)
async def delete_platform_endpoint(platform_id: str, db: AsyncSession = Depends(get_db)):
    """删除平台配置。"""
    success = await delete_platform(db, platform_id)
    if not success:
        raise HTTPException(status_code=404, detail="平台配置不存在")
    invalidate_platform_cache()
    logger.info("平台配置已删除: %s", platform_id)


@router.post("/{platform_id}/test", response_model=PlatformTestResult)
async def test_platform_connection_endpoint(platform_id: str, db: AsyncSession = Depends(get_db)):
    """测试平台连接 — 对 NextFind 调 /quota，对 MoviePilot 调 /site/statistic。"""
    config = await db.get(PlatformConfig, platform_id)
    if not config:
        raise HTTPException(status_code=404, detail="平台配置不存在")
    return await test_platform_connection(config)
