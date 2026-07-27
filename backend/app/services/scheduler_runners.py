"""调度器 Runner 集合 — 供 scheduler 模块调用的各类定时任务入口。

从 main.py 抽离，保持 lifespan 简洁。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.core.logger import init_logger
from app.services import get_emby_service, get_mp_service, get_nf_service, get_tmdb_service
from app.services.emby_scan import EmbyScanService

logger = init_logger()


async def _run_nf_sync(db: AsyncSession) -> None:
    """执行 NF 订阅同步（共用逻辑）。"""
    from app.services.orchestrator import OrchestratorService

    nf = await get_nf_service(db)
    if not nf:
        logger.warning("NF 同步跳过: NextFind 未配置或未启用")
        return
    mp = await get_mp_service(db)
    orchestrator = OrchestratorService(nf, mp)
    results = await orchestrator.sync_subscriptions(db)
    logger.info("NF 订阅同步完成: %d 条记录", len(results))


async def light_scan_runner() -> None:
    """轻量刷新 runner — 只刷新 Emby 缓存 + 补充缺失 TMDB 数据。"""
    async with async_session() as scan_db:
        emby = await get_emby_service(scan_db)
        tmdb = await get_tmdb_service(scan_db)
        if not emby or not tmdb:
            logger.warning("调度器轻量刷新跳过: Emby 或 TMDB 未配置")
            return
        await EmbyScanService.run_light_scan(scan_db, emby, tmdb)


async def full_scan_runner() -> None:
    """全量扫描 runner — 三步全流程。"""
    async with async_session() as scan_db:
        emby = await get_emby_service(scan_db)
        tmdb = await get_tmdb_service(scan_db)
        if not emby or not tmdb:
            logger.warning("调度器全量扫描跳过: Emby 或 TMDB 未配置")
            return
        nf = await get_nf_service(scan_db)
        mp = await get_mp_service(scan_db)
        await EmbyScanService.run_full_scan(scan_db, emby, tmdb, nf, mp)


async def auto_subscribe_runner() -> None:
    """自动订阅 runner，完成后自动触发 NF 同步。"""
    from app.services.auto_subscribe.service import get_auto_subscribe_service

    async with async_session() as subscription_db:
        result = await get_auto_subscribe_service().run(subscription_db, trigger="scheduled")
        if result.get("success"):
            await _run_nf_sync(subscription_db)


async def sync_runner() -> None:
    """NF 订阅同步 runner，使用独立数据库会话。"""
    async with async_session() as sync_db:
        await _run_nf_sync(sync_db)


async def tmdb_sync_runner() -> None:
    """TMDB 增量刷新 runner — 通过 NF 数据判断哪些需要刷新，不批量全扫。"""
    async with async_session() as scan_db:
        nf = await get_nf_service(scan_db)
        tmdb = await get_tmdb_service(scan_db)
        if not nf or not tmdb:
            logger.warning("TMDB 增量刷新跳过: NF 或 TMDB 未配置")
            return
        from app.services.orchestrator import OrchestratorService

        orchestrator = OrchestratorService(nf, tmdb_service=tmdb)
        result = await orchestrator.sync_tmdb_from_nf(scan_db)
        logger.info("TMDB 增量刷新完成: %s", result)
