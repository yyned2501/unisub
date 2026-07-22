"""看板数据库操作封装 — 统计、平台状态、活动日志。

将 routers/dashboard.py 中的数据库查询逻辑封装到此处，
遵循 routers → services → models 的调用链。
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.emby_cache import EmbyCache
from app.models.platform_config import PlatformConfig
from app.models.subscription import Subscription
from app.models.tmdb_cache import TmdbCache
from app.schemas.dashboard import DashboardStats, PlatformStatus


async def get_dashboard_stats(db: AsyncSession) -> DashboardStats:
    """获取订阅统计数据。

    Args:
        db: 数据库会话

    Returns:
        统计数据
    """
    total_result = await db.execute(select(func.count(Subscription.id)))
    total = total_result.scalar() or 0

    movie_result = await db.execute(select(func.count(Subscription.id)).where(Subscription.media_type == "movie"))
    movie_count = movie_result.scalar() or 0

    tv_result = await db.execute(select(func.count(Subscription.id)).where(Subscription.media_type == "tv"))
    tv_count = tv_result.scalar() or 0

    # 缺集数（从 emby_cache + tmdb_cache 计算）
    emby_all = await db.execute(select(EmbyCache.tmdb_id, EmbyCache.emby_episode_count))
    emby_rows = emby_all.all()
    emby_map = {r.tmdb_id: r.emby_episode_count for r in emby_rows}

    missing_count = 0
    if emby_map:
        tmdb_all = await db.execute(
            select(TmdbCache.tmdb_id, TmdbCache.tmdb_aired_eps, TmdbCache.tmdb_total_eps).where(
                TmdbCache.tmdb_id.in_(list(emby_map.keys()))
            )
        )
        for r in tmdb_all.all():
            emby_count = emby_map.get(r.tmdb_id)
            if emby_count is None:
                continue
            aired = r.tmdb_aired_eps or r.tmdb_total_eps
            if aired and aired > emby_count:
                missing_count += 1

    completed_result = await db.execute(select(func.count(Subscription.id)).where(Subscription.completed == True))
    completed_count = completed_result.scalar() or 0

    # TMDB 数据覆盖率（从 tmdb_cache 统计）
    tmdb_total_result = await db.execute(select(func.count(TmdbCache.tmdb_id)))
    tmdb_cached_total = tmdb_total_result.scalar() or 0

    tmdb_filled_result = await db.execute(
        select(func.count(TmdbCache.tmdb_id)).where(
            (TmdbCache.tmdb_total_eps.isnot(None)) | (TmdbCache.tmdb_aired_eps.isnot(None))
        )
    )
    tmdb_data_filled = tmdb_filled_result.scalar() or 0

    return DashboardStats(
        total_subscriptions=total,
        movie_count=movie_count,
        tv_count=tv_count,
        missing_count=missing_count,
        completed_count=completed_count,
        tmdb_cached_total=tmdb_cached_total,
        tmdb_data_filled=tmdb_data_filled,
    )


async def get_platform_statuses(db: AsyncSession) -> list[PlatformStatus]:
    """获取所有平台的连接状态。

    Args:
        db: 数据库会话

    Returns:
        平台状态列表
    """
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
                message = (
                    f"连接正常 ({len(sites) if isinstance(sites, list) else 0} 个站点)" if connected else "连接失败"
                )
            elif config.name == "emby":
                from app.services.emby import EmbyService

                emby = EmbyService(config.base_url, config.api_key)
                info = await emby.test_connection()
                connected = "error" not in info and "ServerName" in info
                message = f"Emby 连接正常: {info.get('ServerName')}" if connected else "连接失败"
            elif config.name == "tmdb":
                from app.services.tmdb import TMDBService

                tmdb = TMDBService(config.api_key, config.base_url)
                conf = await tmdb._get("/configuration")
                connected = "error" not in conf and "images" in conf
                message = "连接正常" if connected else f"连接失败: {conf.get('status_message', conf.get('error', ''))}"
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


async def get_recent_activities(db: AsyncSession, limit: int = 50) -> list[ActivityLog]:
    """获取最近活动日志。

    Args:
        db: 数据库会话
        limit: 返回条数上限

    Returns:
        活动日志列表
    """
    result = await db.execute(select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(limit))
    return list(result.scalars().all())
