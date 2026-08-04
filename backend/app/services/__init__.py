"""服务层 — 统一导出所有 Service 类与工厂函数。

提供辅助函数用于从数据库配置创建服务实例，以及新封装的 DB 操作模块。
平台配置带 60s TTL 内存缓存，避免每次请求都查库。
"""

import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.platform_config import PlatformConfig
from app.services.activity import log_activity
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
    "invalidate_platform_cache",
    "log_activity",
]

# === 平台配置 TTL 缓存（60 秒） ===
# 缓存纯数据快照而非 ORM 对象：ORM 实例绑定请求会话，跨会话共享在
# expire_on_commit 等设置变化时会触发 DetachedInstanceError。


@dataclass(frozen=True, slots=True)
class _PlatformSnapshot:
    """平台配置纯数据快照 — 工厂函数仅需 base_url / api_key。"""

    base_url: str
    api_key: str


_CACHE_TTL = 60.0
_platform_cache: dict[str, tuple[float, _PlatformSnapshot | None]] = {}


def invalidate_platform_cache(name: str | None = None) -> None:
    """主动失效平台配置缓存。name=None 时清空全部。"""
    if name is None:
        _platform_cache.clear()
    else:
        _platform_cache.pop(name, None)


async def _get_platform_config(db: AsyncSession, name: str) -> _PlatformSnapshot | None:
    """从数据库读取指定平台配置（带 TTL 缓存，存纯数据快照）。"""
    now = time.monotonic()
    cached = _platform_cache.get(name)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    stmt = select(PlatformConfig).where(
        PlatformConfig.name == name,
        PlatformConfig.enabled == True,
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    snapshot = _PlatformSnapshot(base_url=row.base_url, api_key=row.api_key) if row else None
    _platform_cache[name] = (now, snapshot)
    return snapshot


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
