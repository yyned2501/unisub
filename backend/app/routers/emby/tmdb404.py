"""Emby TMDB-404 修复路由 — 无效 TMDB ID 剧集的识别与 CD2 整理。

从 routers/emby.py 拆出：列出 Emby 有而 TMDB 无数据的剧集，
借助 CloudDrive2 验证真实路径或移动到待整理目录。
与主路由共用 /api/emby 前缀与鉴权依赖。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.logger import init_logger
from app.schemas.emby_cache import Tmdb404Item
from app.services import log_activity
from app.services.cd2_config import get_cd2_config
from app.services.clouddrive2 import CloudDrive2Service
from app.services.emby.db import list_tmdb_404_items

router = APIRouter(prefix="/api/emby", tags=["Emby 媒体库"], dependencies=[Depends(get_current_user)])
logger = init_logger()


@router.get("/tmdb-404", response_model=list[Tmdb404Item])
async def list_tmdb_404(db: AsyncSession = Depends(get_db)):
    """列出 Emby 中有但 TMDB 中无对应数据的剧集（无效 TMDB ID）。"""
    cd2_config = await get_cd2_config(db)
    items = await list_tmdb_404_items(db, cd2_config)
    return [Tmdb404Item(**item) for item in items]


@router.post("/tmdb-404/{tmdb_id}/resolve")
async def resolve_tmdb_404_path(
    tmdb_id: int,
    db: AsyncSession = Depends(get_db),
):
    """通过 CD2 gRPC 验证并确认真实路径。"""
    cd2_config = await get_cd2_config(db)
    if not cd2_config.base_url or not cd2_config.api_key:
        raise HTTPException(status_code=503, detail="CloudDrive2 未配置")
    if not cd2_config.enabled:
        raise HTTPException(status_code=503, detail="CloudDrive2 已停用")

    items = await list_tmdb_404_items(db, cd2_config)
    matched = [item for item in items if item["tmdb_id"] == tmdb_id]
    if not matched:
        raise HTTPException(status_code=404, detail="未找到该剧集的 Emby 缓存记录")
    item = matched[0]

    cd2_path = item.get("cd2_path")
    if not cd2_path:
        raise HTTPException(status_code=400, detail="该剧集没有路径信息，无法在 CD2 中定位")

    service = CloudDrive2Service(cd2_config.base_url, cd2_config.api_key)
    return await service.resolve_path(cd2_path)


@router.post("/tmdb-404/{tmdb_id}/move")
async def move_tmdb_404_to_pending(
    tmdb_id: int,
    db: AsyncSession = Depends(get_db),
):
    """将无效 TMDB ID 的剧集文件夹通过 CD2 移动到待整理目录。"""
    cd2_config = await get_cd2_config(db)
    if not cd2_config.base_url or not cd2_config.api_key:
        raise HTTPException(status_code=503, detail="CloudDrive2 未配置")
    if not cd2_config.enabled:
        raise HTTPException(status_code=503, detail="CloudDrive2 已停用")

    items = await list_tmdb_404_items(db, cd2_config)
    matched = [item for item in items if item["tmdb_id"] == tmdb_id]
    if not matched:
        raise HTTPException(status_code=404, detail="未找到该剧集的 Emby 缓存记录")
    item = matched[0]

    emby_path = item.get("emby_path")
    cd2_src_path = item.get("cd2_path")
    if not emby_path or not cd2_src_path:
        raise HTTPException(status_code=400, detail="该剧集没有 Emby 路径信息，请先同步缓存")

    service = CloudDrive2Service(cd2_config.base_url, cd2_config.api_key)
    try:
        await service.move_to_pending(cd2_src_path, cd2_config.target_path)
    except RuntimeError as e:
        await log_activity(db, "sync", f"CD2 移动失败: {item['emby_series_name']} (tmdb_id={tmdb_id})", tmdb_id=tmdb_id)
        await db.commit()
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        logger.error("CD2 移动异常: %s", e)
        raise HTTPException(status_code=500, detail=f"CD2 移动异常: {e}") from e

    await log_activity(db, "sync", f"CD2 移动待整理: {item['emby_series_name']} (tmdb_id={tmdb_id})", tmdb_id=tmdb_id)
    await db.commit()
    logger.info("CD2 移动成功: %s (tmdb_id=%s)", item["emby_series_name"], tmdb_id)
    return {"success": True, "message": f"已移动至待整理目录: {item['emby_series_name']}"}
