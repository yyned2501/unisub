"""服务层 — 统一导出所有 Service 类与工厂函数。

提供辅助函数用于从数据库配置创建服务实例，以及新封装的 DB 操作模块。
"""

import uuid
from datetime import UTC, datetime

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.activity_log import ActivityLog
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
    "require_emby_service",
    "require_mp_service",
    "require_nf_service",
    "require_tmdb_service",
    "log_activity",
]


async def _get_platform_config(db: AsyncSession, name: str) -> PlatformConfig | None:
    """从数据库读取指定平台配置。"""
    stmt = select(PlatformConfig).where(
        PlatformConfig.name == name,
        PlatformConfig.enabled == True,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_nf_service(db: AsyncSession) -> NextFindService | None:
    """从数据库读取 NextFind 平台配置并创建服务实例。"""
    config = await _get_platform_config(db, "nextfind")
    if not config:
        return None
    return NextFindService(config.base_url, config.api_key)


async def get_mp_service(db: AsyncSession) -> MoviePilotService | None:
    """从数据库读取 MoviePilot 平台配置并创建服务实例。"""
    config = await _get_platform_config(db, "moviepilot")
    if not config:
        return None
    return MoviePilotService(config.base_url, config.api_key)


async def get_emby_service(db: AsyncSession) -> EmbyService | None:
    """从数据库读取 Emby 平台配置并创建服务实例。"""
    config = await _get_platform_config(db, "emby")
    if not config:
        return None
    return EmbyService(config.base_url, config.api_key)


async def get_tmdb_service(db: AsyncSession) -> TMDBService | None:
    """从数据库读取 TMDB 平台配置并创建服务实例。"""
    config = await _get_platform_config(db, "tmdb")
    if not config:
        return None
    return TMDBService(config.api_key, config.base_url)


# === FastAPI 依赖注入版本 — 未配置时自动 503 ===


async def require_nf_service(db: AsyncSession = Depends(get_db)) -> NextFindService:
    """NextFind 服务依赖 — 未配置时抛出 503。"""
    nf = await get_nf_service(db)
    if not nf:
        raise HTTPException(status_code=503, detail="NextFind 平台未配置或未启用")
    return nf


async def require_mp_service(db: AsyncSession = Depends(get_db)) -> MoviePilotService:
    """MoviePilot 服务依赖 — 未配置时抛出 503。"""
    mp = await get_mp_service(db)
    if not mp:
        raise HTTPException(status_code=503, detail="MoviePilot 平台未配置或未启用")
    return mp


async def require_emby_service(db: AsyncSession = Depends(get_db)) -> EmbyService:
    """Emby 服务依赖 — 未配置时抛出 503。"""
    emby = await get_emby_service(db)
    if not emby:
        raise HTTPException(status_code=503, detail="Emby 平台未配置或未启用")
    return emby


async def require_tmdb_service(db: AsyncSession = Depends(get_db)) -> TMDBService:
    """TMDB 服务依赖 — 未配置时抛出 503。"""
    tmdb = await get_tmdb_service(db)
    if not tmdb:
        raise HTTPException(status_code=503, detail="TMDB 平台未配置或未启用")
    return tmdb


# === 通用活动日志 ===


async def log_activity(
    db: AsyncSession,
    action: str,
    message: str,
    tmdb_id: int | None = None,
) -> None:
    """写入活动日志。

    Args:
        db: 数据库会话
        action: 操作类型（subscribe / unsubscribe / sync / system 等）
        message: 日志消息
        tmdb_id: 关联的 TMDB ID（可选）
    """
    entry = ActivityLog(
        id=str(uuid.uuid4()),
        action=action,
        tmdb_id=tmdb_id,
        message=message,
        created_at=datetime.now(UTC),
    )
    db.add(entry)
