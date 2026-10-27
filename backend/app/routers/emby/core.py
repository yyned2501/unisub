"""Emby 媒体库路由 — 缺集分析（从缓存表读取）+ 缓存同步 + 黑名单。

TMDB-404 修复端点见 emby/tmdb404.py（共用 /api/emby 前缀）。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import async_session, get_db
from app.core.logger import init_logger
from app.core.tasks import spawn_background_task
from app.models.emby_cache import EmbyCache
from app.schemas.emby import (
    BlacklistActionResponse,
    BlacklistCreate,
    EmbyActionResponse,
    EmbyBlacklistEntry,
    EmbySubscribeRequest,
)
from app.schemas.emby_cache import EmbyMissingAnalysis, EmbySyncResult
from app.services import (
    get_mp_service,
    get_nf_service,
    get_tmdb_service,
    log_activity,
    require_emby_service,
    require_nf_service,
    require_tmdb_service,
)
from app.services.emby.db import (
    add_blacklist_entry,
    analyze_missing_library,
    list_blacklist,
    remove_blacklist_entry,
)
from app.services.emby.scan import EmbyScanService
from app.services.emby.service import EmbyService
from app.services.nextfind import NextFindService
from app.services.orchestrator.service import OrchestratorService
from app.services.tmdb.service import TMDBService

router = APIRouter(prefix="/api/emby", tags=["Emby 媒体库"], dependencies=[Depends(get_current_user)])
logger = init_logger()


@router.post("/sync-cache", response_model=EmbySyncResult)
async def sync_cache(
    db: AsyncSession = Depends(get_db),
    emby: EmbyService = Depends(require_emby_service),
):
    """手动触发 Emby 缓存同步 — 拉取 Emby 剧集数据写入 emby_cache（不包括 TMDB 数据）。"""
    result = await emby.sync_cache(db)

    return EmbySyncResult(
        success=True,
        total_synced=result["synced"],
        message=f"同步完成: {result['synced']} 条更新, {result['deleted']} 条删除",
    )


@router.post("/update-tmdb", response_model=EmbySyncResult)
async def update_tmdb(
    db: AsyncSession = Depends(get_db),
    emby: EmbyService = Depends(require_emby_service),
    tmdb: TMDBService = Depends(require_tmdb_service),
):
    """补充 emby_cache 的 TMDB 数据（只更新已订阅剧集）。"""
    result = await emby.update_tmdb_data(db, tmdb)

    return EmbySyncResult(
        success=True,
        total_synced=result["updated"],
        message=f"TMDB 数据更新完成: {result['updated']} 条",
    )


@router.post("/backfill-overview")
async def backfill_overview_endpoint(
    db: AsyncSession = Depends(get_db),
    emby: EmbyService = Depends(require_emby_service),
    tmdb: TMDBService = Depends(require_tmdb_service),
):
    """从 TMDB 为缺少描述的剧集补充 overview，写入本地缓存并同步到 Emby。"""
    result = await emby.backfill_overview(db, tmdb)
    logger.info(f"Overview 回填: {result}")
    return {
        "success": True,
        "checked": result["checked"],
        "filled": result["filled"],
        "message": (
            f"补充完成: 检查 {result['checked']} 条, 成功 {result['filled']} 条, TMDB 无描述 {result['no_tmdb']} 条"
        ),
    }


@router.get("/library-analysis", response_model=EmbyMissingAnalysis)
async def analyze_missing(
    page: int = 1,
    page_size: int = 50,
    library: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """从缓存表读取 Emby 剧集数据，支持分页和媒体库过滤。

    从 emby_cache 表读取，关联订阅表和黑名单表，
    只展示缺集数 > 0（emby_episode_count < tmdb_aired_eps）的条目。

    Args:
        page: 页码（从 1 开始）
        page_size: 每页条数
        library: 媒体库名称过滤
    """
    return await analyze_missing_library(db, page=page, page_size=page_size, library_name=library)


@router.get("/blacklist", response_model=list[EmbyBlacklistEntry])
async def list_blacklist_endpoint(db: AsyncSession = Depends(get_db)):
    """获取所有黑名单条目。"""
    entries = await list_blacklist(db)
    return [EmbyBlacklistEntry(tmdb_id=e.tmdb_id, created_at=e.created_at) for e in entries]


@router.post("/blacklist", response_model=BlacklistActionResponse, status_code=201)
async def add_to_blacklist(body: BlacklistCreate, db: AsyncSession = Depends(get_db)):
    """添加 TMDB ID 到黑名单。"""
    result = await add_blacklist_entry(db, body.tmdb_id)
    logger.info(f"添加黑名单: tmdb_id={body.tmdb_id}, {result['message']}")
    return BlacklistActionResponse(success=result["success"], message=result["message"])


@router.delete("/blacklist/{tmdb_id}", response_model=BlacklistActionResponse)
async def remove_from_blacklist(tmdb_id: int, db: AsyncSession = Depends(get_db)):
    """从黑名单移除 TMDB ID。"""
    result = await remove_blacklist_entry(db, tmdb_id)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["message"])
    logger.info(f"移除黑名单: tmdb_id={tmdb_id}")
    return BlacklistActionResponse(success=True, message=result["message"])


@router.post("/scan")
async def trigger_scan(
    db: AsyncSession = Depends(get_db),
    emby: EmbyService = Depends(require_emby_service),
    tmdb: TMDBService = Depends(require_tmdb_service),
):
    """手动触发一键 Emby 扫描 — sync-cache → update-tmdb → sync-subscriptions。"""
    status = EmbyScanService.get_status()
    if status["running"]:
        raise HTTPException(status_code=409, detail="扫描已在进行中")

    # nf / mp 为可选（仅同步订阅步骤需要）
    nf = await get_nf_service(db)
    mp = await get_mp_service(db)

    # 后台异步执行 — 需要独立 session（Depends 的 session 会随请求关闭）
    async def _run_scan():
        async with async_session() as scan_db:
            await EmbyScanService.run_full_scan(scan_db, emby, tmdb, nf, mp)

    spawn_background_task(_run_scan(), "emby-full-scan")

    return {"success": True, "message": "扫描已启动"}


@router.get("/scan-status")
async def get_scan_status():
    """获取当前扫描进度。"""
    return EmbyScanService.get_status()


@router.post("/subscribe", response_model=EmbyActionResponse)
async def subscribe_from_emby(
    body: EmbySubscribeRequest,
    db: AsyncSession = Depends(get_db),
    nf: NextFindService = Depends(require_nf_service),
):
    """从 Emby 缺集列表添加订阅 — 调用 NextFind 订阅 + 创建本地记录。"""
    mp = await get_mp_service(db)
    tmdb = await get_tmdb_service(db)
    orchestrator = OrchestratorService(nf, mp, tmdb)

    try:
        sub = await orchestrator.subscribe(
            db=db,
            tmdb_id=body.tmdb_id,
            title=body.title,
            media_type=body.media_type,
            poster_url=body.poster_url,
            year=body.year,
        )
        logger.info(f"Emby 缺集添加订阅: {body.title} (tmdb_id={body.tmdb_id})")
        return EmbyActionResponse(
            success=True,
            message=f"已添加订阅: {sub.title}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Emby 添加订阅失败: {e}")
        raise HTTPException(status_code=500, detail=f"添加订阅失败: {e}")


@router.delete("/item/{tmdb_id}", response_model=EmbyActionResponse)
async def delete_from_emby(
    tmdb_id: int,
    db: AsyncSession = Depends(get_db),
    emby: EmbyService = Depends(require_emby_service),
):
    """从 Emby 删除指定 tmdb_id 对应的媒体项。

    ⚠️ 不可逆操作：会删除 Emby 中的媒体项及其本地文件。删除成功后同步
    移除 emby_cache 记录，避免下次缺集分析再次列出。
    """
    cache = (await db.execute(select(EmbyCache).where(EmbyCache.tmdb_id == tmdb_id))).scalar_one_or_none()
    if not cache:
        raise HTTPException(status_code=404, detail="未找到该剧集的 Emby 缓存记录")
    if not cache.emby_series_id:
        raise HTTPException(status_code=400, detail="该剧集没有 Emby ID，请先同步缓存")

    title = cache.emby_series_name or str(tmdb_id)
    emby_id = cache.emby_series_id
    result = await emby.delete_item(emby_id)
    if "error" in result:
        detail = result.get("detail") or result.get("error")
        raise HTTPException(status_code=502, detail=f"Emby 删除失败: {detail}")

    # 删除成功后移除缓存记录并记日志
    await db.delete(cache)
    await log_activity(db, "system", f"从 Emby 删除: {title} (tmdb_id={tmdb_id})", tmdb_id=tmdb_id)
    await db.commit()
    logger.info(f"从 Emby 删除成功: {title} (tmdb_id={tmdb_id}, emby_id={emby_id})")
    return EmbyActionResponse(success=True, message=f"已从 Emby 删除: {title}")
