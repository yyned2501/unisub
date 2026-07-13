"""看板路由 — 统计、平台状态、活动日志、NextFind 额度。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import init_logger
from app.models.activity_log import ActivityLog
from app.models.platform_config import PlatformConfig
from app.models.subscription import Subscription
from app.schemas.dashboard import (
    ActivityLogResponse,
    DashboardStats,
    NextFindQuota,
    PlatformStatus,
)
from app.services import get_mp_service, get_nf_service

router = APIRouter(prefix="/api/dashboard", tags=["看板"])
logger = init_logger()


@router.get("/stats", response_model=DashboardStats)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """获取订阅统计数据。"""
    # 总数
    total_result = await db.execute(select(func.count(Subscription.id)))
    total = total_result.scalar() or 0

    # 电影数
    movie_result = await db.execute(
        select(func.count(Subscription.id)).where(
            Subscription.media_type == "movie"
        )
    )
    movie_count = movie_result.scalar() or 0

    # 剧集数
    tv_result = await db.execute(
        select(func.count(Subscription.id)).where(
            Subscription.media_type == "tv"
        )
    )
    tv_count = tv_result.scalar() or 0

    # 缺集数
    missing_result = await db.execute(
        select(func.count(Subscription.id)).where(
            Subscription.nf_missing_eps > 0
        )
    )
    missing_count = missing_result.scalar() or 0

    # 已完成数
    completed_result = await db.execute(
        select(func.count(Subscription.id)).where(
            Subscription.completed == True
        )
    )
    completed_count = completed_result.scalar() or 0

    return DashboardStats(
        total_subscriptions=total,
        movie_count=movie_count,
        tv_count=tv_count,
        missing_eps_count=missing_count,
        completed_count=completed_count,
    )


@router.get("/platforms", response_model=list[PlatformStatus])
async def get_platform_status(db: AsyncSession = Depends(get_db)):
    """获取所有平台的连接状态。"""
    result = await db.execute(select(PlatformConfig))
    configs = result.scalars().all()

    statuses: list[PlatformStatus] = []
    for config in configs:
        connected = False
        message = "未检测"

        try:
            if config.name == "nextfind":
                from app.services.nextfind import NextFindService
                nf = NextFindService(config.base_url, config.api_key)
                quota = await nf.get_quota()
                connected = "error" not in quota
                message = "连接正常" if connected else f"连接失败: {quota.get('detail', '')}"
            elif config.name == "moviepilot":
                from app.services.moviepilot import MoviePilotService
                mp = MoviePilotService(config.base_url, config.api_key)
                sites = await mp.get_site_statistic()
                connected = isinstance(sites, list)
                message = f"连接正常 ({len(sites) if isinstance(sites, list) else 0} 个站点)" if connected else "连接失败"
        except Exception as e:
            message = f"连接异常: {str(e)}"

        statuses.append(
            PlatformStatus(
                name=config.name,
                enabled=config.enabled,
                connected=connected,
                message=message,
            )
        )

    return statuses


@router.get("/activities", response_model=list[ActivityLogResponse])
async def get_activities(
    limit: int = 50, db: AsyncSession = Depends(get_db)
):
    """获取最近活动日志。"""
    result = await db.execute(
        select(ActivityLog)
        .order_by(ActivityLog.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/nextfind-quota", response_model=NextFindQuota)
async def get_nextfind_quota(db: AsyncSession = Depends(get_db)):
    """获取 NextFind 积分/额度信息。"""
    nf = await get_nf_service(db)
    if not nf:
        raise HTTPException(status_code=503, detail="NextFind 平台未配置或未启用")

    result = await nf.get_quota()
    if "error" in result:
        return NextFindQuota(
            quota=None,
            error=result.get("detail", result["error"]),
        )
    return NextFindQuota(quota=result)
