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
from app.services.emby import EmbyService
from app.services.moviepilot import MoviePilotService
from app.services.nextfind import NextFindService
from app.services.platform import create_platform, delete_platform, list_platforms, update_platform

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
        logger.info(f"平台配置已创建: {body.name}")
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
    logger.info(f"平台配置已更新: {config.name}")
    return config


@router.delete("/{platform_id}", status_code=204)
async def delete_platform_endpoint(platform_id: str, db: AsyncSession = Depends(get_db)):
    """删除平台配置。"""
    success = await delete_platform(db, platform_id)
    if not success:
        raise HTTPException(status_code=404, detail="平台配置不存在")
    logger.info(f"平台配置已删除: {platform_id}")


@router.post("/{platform_id}/test", response_model=PlatformTestResult)
async def test_platform_connection(platform_id: str, db: AsyncSession = Depends(get_db)):
    """测试平台连接 — 对 NextFind 调 /quota，对 MoviePilot 调 /site/statistic。"""
    config = await db.get(PlatformConfig, platform_id)
    if not config:
        raise HTTPException(status_code=404, detail="平台配置不存在")

    try:
        if config.name == "nextfind":
            service = NextFindService(config.base_url, config.api_key)
            result = await service.get_quota()
            if "error" in result:
                return PlatformTestResult(
                    success=False,
                    message=f"连接失败: {result.get('detail', result['error'])}",
                    details=result,
                )
            return PlatformTestResult(
                success=True,
                message="NextFind 连接正常",
                details=result,
            )
        elif config.name == "moviepilot":
            service = MoviePilotService(config.base_url, config.api_key)
            result = await service.get_site_statistic()
            return PlatformTestResult(
                success=True,
                message="MoviePilot 连接正常",
                details={"sites": len(result) if isinstance(result, list) else 0},
            )
        elif config.name == "emby":
            service = EmbyService(config.base_url, config.api_key)
            result = await service.test_connection()
            if "error" in result or "ServerName" not in result:
                return PlatformTestResult(
                    success=False,
                    message=f"连接失败: {result.get('detail', result.get('error', '未知错误'))}",
                    details=result,
                )
            return PlatformTestResult(
                success=True,
                message=f"Emby 连接正常: {result.get('ServerName')}",
                details={"ServerName": result.get("ServerName"), "Version": result.get("Version")},
            )
        else:
            return PlatformTestResult(
                success=False,
                message=f"未知平台类型: {config.name}",
            )
    except Exception as e:
        logger.error(f"平台连接测试异常 ({config.name}): {e}")
        return PlatformTestResult(
            success=False,
            message=f"连接测试异常: {str(e)}",
        )
