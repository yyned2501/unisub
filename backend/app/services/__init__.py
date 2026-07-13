"""服务层 — NextFind / MoviePilot API 封装与编排逻辑。

提供辅助函数用于从数据库配置创建服务实例。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_config import PlatformConfig
from app.services.nextfind import NextFindService
from app.services.moviepilot import MoviePilotService


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
