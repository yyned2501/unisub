"""看板路由 — 统计、平台状态、活动日志、NextFind 额度。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.logger import init_logger
from app.schemas.dashboard import (
    ActivityLogResponse,
    DashboardStats,
    NextFindQuota,
    PlatformStatus,
)
from app.services import require_nf_service
from app.services.dashboard import get_dashboard_stats, get_platform_statuses, get_recent_activities
from app.services.nextfind import NextFindService

router = APIRouter(prefix="/api/dashboard", tags=["看板"], dependencies=[Depends(get_current_user)])
logger = init_logger()


@router.get("/stats", response_model=DashboardStats)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """获取订阅统计数据。"""
    return await get_dashboard_stats(db)


@router.get("/platforms", response_model=list[PlatformStatus])
async def get_platform_status(db: AsyncSession = Depends(get_db)):
    """获取所有平台的连接状态。"""
    return await get_platform_statuses(db)


@router.get("/activities", response_model=list[ActivityLogResponse])
async def get_activities(limit: int = 10, db: AsyncSession = Depends(get_db)):
    """获取最近活动日志。"""
    return await get_recent_activities(db, limit)


@router.get("/nextfind-quota", response_model=NextFindQuota)
async def get_nextfind_quota(nf: NextFindService = Depends(require_nf_service)):
    """获取 NextFind 积分/额度信息。"""
    result = await nf.get_quota()
    if "error" in result:
        return NextFindQuota(
            quota=None,
            error=result.get("detail", result["error"]),
        )
    return NextFindQuota(quota=result)
