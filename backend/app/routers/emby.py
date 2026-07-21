"""Emby 媒体库路由 — 缺集分析（从缓存表读取）+ 缓存同步 + 黑名单。"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import async_session, get_db
from app.core.logger import init_logger
from app.schemas.emby import (
    BlacklistActionResponse,
    BlacklistCreate,
    EmbyActionRequest,
    EmbyActionResponse,
    EmbyBlacklistEntry,
    EmbySubscribeRequest,
)
from app.schemas.emby_cache import EmbyMissingAnalysis, EmbySyncResult, Tmdb404Item
from app.services import get_emby_service, get_mp_service, get_nf_service, get_tmdb_service
from app.services.cd2_config import get_cd2_config
from app.services.clouddrive2 import CloudDrive2Service
from app.services.emby_db import (
    add_blacklist_entry,
    analyze_missing_library,
    list_blacklist,
    list_tmdb_404_items,
    remove_blacklist_entry,
)
from app.services.emby_scan import EmbyScanService

router = APIRouter(prefix="/api/emby", tags=["Emby 媒体库"], dependencies=[Depends(get_current_user)])
logger = init_logger()


@router.post("/sync-cache", response_model=EmbySyncResult)
async def sync_cache(db: AsyncSession = Depends(get_db)):
    """手动触发 Emby 缓存同步 — 拉取 Emby 剧集数据写入 emby_cache（不包括 TMDB 数据）。"""
    emby = await get_emby_service(db)
    if not emby:
        raise HTTPException(status_code=503, detail="Emby 平台未配置或未启用")

    result = await emby.sync_cache(db)

    return EmbySyncResult(
        success=True,
        total_synced=result["synced"],
        message=f"同步完成: {result['synced']} 条更新, {result['deleted']} 条删除",
    )


@router.post("/update-tmdb", response_model=EmbySyncResult)
async def update_tmdb(db: AsyncSession = Depends(get_db)):
    """补充 emby_cache 的 TMDB 数据（只更新已订阅剧集）。"""
    emby = await get_emby_service(db)
    if not emby:
        raise HTTPException(status_code=503, detail="Emby 平台未配置或未启用")

    tmdb = await get_tmdb_service(db)
    if not tmdb:
        raise HTTPException(status_code=503, detail="TMDB 平台未配置或未启用")

    result = await emby.update_tmdb_data(db, tmdb)

    return EmbySyncResult(
        success=True,
        total_synced=result["updated"],
        message=f"TMDB 数据更新完成: {result['updated']} 条",
    )


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
async def trigger_scan(db: AsyncSession = Depends(get_db)):
    """手动触发一键 Emby 扫描 — sync-cache → update-tmdb → sync-subscriptions。"""
    status = EmbyScanService.get_status()
    if status["running"]:
        raise HTTPException(status_code=409, detail="扫描已在进行中")

    emby = await get_emby_service(db)
    if not emby:
        raise HTTPException(status_code=503, detail="Emby 平台未配置或未启用")

    tmdb = await get_tmdb_service(db)
    if not tmdb:
        raise HTTPException(status_code=503, detail="TMDB 平台未配置或未启用")

    nf = await get_nf_service(db)
    mp = await get_mp_service(db)

    # 后台异步执行 — 需要独立 session（Depends 的 session 会随请求关闭）
    async def _run_scan():
        async with async_session() as scan_db:
            await EmbyScanService.run_full_scan(scan_db, emby, tmdb, nf, mp)

    import asyncio

    asyncio.create_task(_run_scan())

    return {"success": True, "message": "扫描已启动"}


@router.get("/scan-status")
async def get_scan_status():
    """获取当前扫描进度。"""
    return EmbyScanService.get_status()


@router.post("/subscribe", response_model=EmbyActionResponse)
async def subscribe_from_emby(body: EmbySubscribeRequest, db: AsyncSession = Depends(get_db)):
    """从 Emby 缺集列表添加订阅 — 调用 NextFind 订阅 + 创建本地记录。"""
    from app.services.orchestrator import OrchestratorService

    nf = await get_nf_service(db)
    if not nf:
        raise HTTPException(status_code=503, detail="NextFind 平台未配置或未启用")

    mp = await get_mp_service(db)
    orchestrator = OrchestratorService(nf, mp)

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
    except Exception as e:
        logger.error(f"Emby 添加订阅失败: {e}")
        raise HTTPException(status_code=500, detail=f"添加订阅失败: {e}")


@router.post("/fill-missing", response_model=EmbyActionResponse)
async def fill_missing_from_emby(body: EmbyActionRequest, db: AsyncSession = Depends(get_db)):
    """从 Emby 缺集列表触发补缺集 — 调用 NextFind /media/fill_missing。"""
    from app.models.activity_log import ActivityLog

    nf = await get_nf_service(db)
    if not nf:
        raise HTTPException(status_code=503, detail="NextFind 平台未配置或未启用")

    try:
        result = await nf.fill_missing(tmdb_id=body.tmdb_id, media_type="tv")
        if isinstance(result, dict) and result.get("error"):
            logger.error(f"NextFind 补缺集失败: tmdb_id={body.tmdb_id}, {result}")
            return EmbyActionResponse(
                success=False,
                message=f"补缺集失败: {result.get('error', '未知错误')}",
            )

        log_entry = ActivityLog(
            id=str(uuid.uuid4()),
            action="sync",
            tmdb_id=body.tmdb_id,
            message=f"触发补缺集: tmdb_id={body.tmdb_id}",
            created_at=datetime.now(UTC),
        )
        db.add(log_entry)
        await db.commit()

        logger.info(f"Emby 补缺集触发成功: tmdb_id={body.tmdb_id}")
        return EmbyActionResponse(
            success=True,
            message="补缺集已推入高优搜索队列",
        )
    except Exception as e:
        logger.error(f"Emby 补缺集失败: {e}")
        raise HTTPException(status_code=500, detail=f"补缺集失败: {e}")


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

    # 1. 尝试精确查找
    found = await service._client.find_file_by_path(cd2_path)
    if found:
        sub_files = await service._client.list_sub_files(cd2_path)
        return {
            "verified": True,
            "cd2_path": found["path"],
            "name": found["name"],
            "file_type": "directory" if found.get("file_type") == 0 else "file",
            "sub_items": len(sub_files),
            "sub_file_names": [f["name"] for f in sub_files[:20]],
            "note": "CD2 中已确认该路径",
        }

    # 2. 精确查找不到，尝试逐级查找
    parent_path = "/".join(cd2_path.rstrip("/").split("/")[:-1]) or "/"
    folder_name = cd2_path.rstrip("/").split("/")[-1]
    parent_files = await service._client.list_sub_files(parent_path)
    candidates = [f for f in parent_files if folder_name in f["name"]]
    if candidates:
        return {
            "verified": True,
            "cd2_path": candidates[0]["path"],
            "name": candidates[0]["name"],
            "file_type": "directory" if candidates[0].get("is_dir") else "file",
            "sub_items": len(candidates),
            "sub_file_names": [f["name"] for f in candidates],
            "note": "模糊匹配找到的路径，请确认是否正确",
        }

    return {
        "verified": False,
        "cd2_path": cd2_path,
        "note": "CD2 中未找到该路径，请手动检查",
    }


@router.post("/tmdb-404/{tmdb_id}/move")
async def move_tmdb_404_to_pending(
    tmdb_id: int,
    db: AsyncSession = Depends(get_db),
):
    """将无效 TMDB ID 的剧集文件夹通过 CD2 移动到待整理目录。"""
    from app.models.activity_log import ActivityLog

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

    try:
        service = CloudDrive2Service(cd2_config.base_url, cd2_config.api_key)

        # 1. 先重命名文件夹，去掉 {tmdb-xxx} 标记
        import re

        parent_path = "/".join(cd2_src_path.rstrip("/").split("/")[:-1]) or "/"
        folder_name = cd2_src_path.rstrip("/").split("/")[-1]
        new_name = re.sub(r"\s*\{tmdb-\d+\}\s*", "", folder_name).strip()
        if new_name and new_name != folder_name:
            rename_ok = await service._client.rename_file(cd2_src_path, new_name)
            if rename_ok:
                cd2_src_path = f"{parent_path}/{new_name}" if parent_path != "/" else f"/{new_name}"
                logger.info(f"已重命名: {folder_name} → {new_name}")
            else:
                logger.warning(f"重命名失败，继续使用原路径: {folder_name}")
        else:
            new_name = folder_name

        # 2. 确保目标目录存在
        dest = cd2_config.target_path
        await service._client.ensure_directory(dest)

        # 3. 移动文件
        success = await service._client.move_file([cd2_src_path], dest)
        if not success:
            log_entry = ActivityLog(
                id=str(uuid.uuid4()),
                action="sync",
                tmdb_id=tmdb_id,
                message=f"CD2 移动失败: {item['emby_series_name']} (tmdb_id={tmdb_id})",
                created_at=datetime.now(UTC),
            )
            db.add(log_entry)
            await db.commit()
            raise HTTPException(status_code=500, detail="CD2 移动文件失败，请检查路径和权限")

        # 3. 记录活动日志
        log_entry = ActivityLog(
            id=str(uuid.uuid4()),
            action="sync",
            tmdb_id=tmdb_id,
            message=f"CD2 移动待整理: {item['emby_series_name']} (tmdb_id={tmdb_id})",
            created_at=datetime.now(UTC),
        )
        db.add(log_entry)
        await db.commit()

        logger.info(f"CD2 移动成功: {item['emby_series_name']} (tmdb_id={tmdb_id}) → {dest}")
        return {"success": True, "message": f"已移动至待整理目录: {item['emby_series_name']}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CD2 移动异常: {e}")
        raise HTTPException(status_code=500, detail=f"CD2 移动异常: {e}")
