"""服务层 — 统一导出所有 Service 类与工厂函数。

提供辅助函数用于从数据库配置创建服务实例，以及新封装的 DB 操作模块。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_config import PlatformConfig
from app.services.emby import EmbyService
from app.services.forward import ForwardService
from app.services.moviepilot import MoviePilotService
from app.services.nextfind import NextFindService
from app.services.tmdb import TMDBService

__all__ = [
    "ForwardService",
    "MoviePilotService",
    "NextFindService",
    "TMDBService",
    "get_emby_service",
    "get_mp_service",
    "get_nf_service",
    "get_tmdb_service",
]


async def get_nf_service(db: AsyncSession) -> NextFindService | None:
    """从数据库读取 NextFind 平台配置并创建服务实例。"""
    stmt = select(PlatformConfig).where(
        PlatformConfig.name == "nextfind",
        PlatformConfig.enabled == True,
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()
    if not config:
        return None
    return NextFindService(config.base_url, config.api_key)


async def get_mp_service(db: AsyncSession) -> MoviePilotService | None:
    """从数据库读取 MoviePilot 平台配置并创建服务实例。"""
    stmt = select(PlatformConfig).where(
        PlatformConfig.name == "moviepilot",
        PlatformConfig.enabled == True,
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()
    if not config:
        return None
    return MoviePilotService(config.base_url, config.api_key)


async def get_emby_service(db: AsyncSession) -> EmbyService | None:
    """从数据库读取 Emby 平台配置并创建服务实例。"""
    stmt = select(PlatformConfig).where(
        PlatformConfig.name == "emby",
        PlatformConfig.enabled == True,
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()
    if not config:
        return None
    return EmbyService(config.base_url, config.api_key)


async def get_tmdb_service(db: AsyncSession) -> TMDBService | None:
    """从数据库读取 TMDB 平台配置并创建服务实例。"""
    stmt = select(PlatformConfig).where(
        PlatformConfig.name == "tmdb",
        PlatformConfig.enabled == True,
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()
    if not config:
        return None
    return TMDBService(config.api_key, config.base_url)
