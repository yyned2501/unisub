"""CloudDrive2 配置路由。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.logger import init_logger
from app.schemas.cd2 import Cd2ConfigResponse, Cd2ConfigUpdate, Cd2TestResult
from app.services.cd2_config import get_cd2_config, update_cd2_config
from app.services.clouddrive2 import CloudDrive2Service

router = APIRouter(prefix="/api/settings/cd2", tags=["CloudDrive2 配置"], dependencies=[Depends(get_current_user)])
logger = init_logger()


@router.get("", response_model=Cd2ConfigResponse)
async def get_cd2_config_endpoint(
    db: AsyncSession = Depends(get_db),
) -> Cd2ConfigResponse:
    """获取 CloudDrive2 配置。"""
    return await get_cd2_config(db)


@router.put("", response_model=Cd2ConfigResponse)
async def update_cd2_config_endpoint(
    body: Cd2ConfigUpdate,
    db: AsyncSession = Depends(get_db),
) -> Cd2ConfigResponse:
    """保存 CloudDrive2 配置。"""
    try:
        config = await update_cd2_config(
            db,
            base_url=body.base_url,
            api_key=body.api_key,
            target_path=body.target_path,
            enabled=body.enabled,
            path_prefix=body.path_prefix,
            path_replacement=body.path_replacement,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    logger.info("CloudDrive2 配置已更新")
    return config


@router.post("/test", response_model=Cd2TestResult)
async def test_cd2_connection_endpoint(
    db: AsyncSession = Depends(get_db),
) -> Cd2TestResult:
    """测试 CloudDrive2 gRPC 地址及 API Token。"""
    config = await get_cd2_config(db)
    if not config.base_url or not config.api_key:
        return Cd2TestResult(success=False, message="请先填写 URL 和 API Key")

    try:
        details = await CloudDrive2Service(config.base_url, config.api_key).test_connection()
        return Cd2TestResult(
            success=True,
            message="CloudDrive2 连接正常",
            details=details,
        )
    except Exception as exc:
        logger.error("CloudDrive2 连接测试异常: %s", exc)
        return Cd2TestResult(
            success=False,
            message=f"连接测试异常: {exc}",
        )
