"""Emby 一键扫描服务 — 三步全流程 + 内存进度跟踪。

从 emby.py 中拆分，遵守单文件 < 300 行规范。

扫描流程:
    1. sync Emby cache (0-30%)
    2. update TMDB data for all cached (30-80%)
    3. orchestrator sync subscriptions (80-100%)
"""

from datetime import UTC, datetime

from app.core.logger import init_logger
from app.services.emby import EmbyService
from app.services.orchestrator import OrchestratorService
from app.services.tmdb import TMDBService

logger = init_logger()


class EmbyScanService:
    """Emby 一键扫描服务 — 三步全流程 + 内存进度跟踪。

    扫描流程:
        1. sync Emby cache (0-30%)
        2. update TMDB data for all cached (30-80%)
        3. orchestrator sync subscriptions (80-100%)
    """

    _scan_status: dict = {
        "running": False,
        "progress": 0,
        "current_step": 0,
        "total_steps": 3,
        "step_name": "",
        "total_items": 0,
        "current_item": 0,
        "started_at": None,
        "error": None,
    }

    @classmethod
    def get_status(cls) -> dict:
        """获取当前扫描进度状态。"""
        return dict(cls._scan_status)

    @classmethod
    async def run_full_scan(
        cls,
        db,
        emby: EmbyService,
        tmdb: TMDBService,
        nf_service=None,
        mp_service=None,
    ):
        """执行完整 Emby 扫描流程。

        三步: sync-cache → update-tmdb-all → sync-subscriptions

        Args:
            db: 数据库会话
            emby: Emby 服务实例
            tmdb: TMDB 服务实例
            nf_service: NextFind 服务实例（可选，sync 步骤需要）
            mp_service: MoviePilot 服务实例（可选）
        """
        if cls._scan_status["running"]:
            logger.warning("扫描已在进行中，跳过")
            return

        cls._scan_status["running"] = True
        cls._scan_status["progress"] = 0
        cls._scan_status["error"] = None
        cls._scan_status["started_at"] = datetime.now(UTC).isoformat()

        try:
            # Step 1: Sync Emby cache (0-30%)
            cls._scan_status["current_step"] = 1
            cls._scan_status["step_name"] = "正在同步 Emby 缓存..."
            cls._scan_status["total_items"] = 0
            cls._scan_status["current_item"] = 0
            logger.info("扫描 Step 1/3: 同步 Emby 缓存")
            sync_result = await emby.sync_cache(db)

            cls._scan_status["progress"] = 30
            logger.info(f"扫描 Step 1/3 完成: {sync_result}")

            # Step 2: Update TMDB data for all cached (30-80%)
            cls._scan_status["current_step"] = 2
            cls._scan_status["step_name"] = "正在更新 TMDB 数据..."
            cls._scan_status["total_items"] = 0
            cls._scan_status["current_item"] = 0

            async def _tmdb_progress(current, total):
                cls._scan_status["total_items"] = total
                cls._scan_status["current_item"] = current
                pct = 30 + int((current / total) * 50) if total > 0 else 30
                cls._scan_status["progress"] = min(pct, 80)

            logger.info("扫描 Step 2/3: 更新 TMDB 数据（全量）")
            tmdb_result = await emby.update_tmdb_data_all(
                db,
                tmdb,
                progress_callback=_tmdb_progress,
            )

            # 补充缺失描述：TMDB 有描述的写入 emby_cache 并同步到 Emby（仅处理空 overview 条目）
            cls._scan_status["step_name"] = "正在补充缺失描述..."
            overview_result = await emby.backfill_overview(db, tmdb)
            logger.info(f"扫描 描述补充完成: {overview_result}")

            cls._scan_status["progress"] = 80
            logger.info(f"扫描 Step 2/3 完成: {tmdb_result}")

            # Step 3: Sync subscriptions (80-100%)
            cls._scan_status["current_step"] = 3
            cls._scan_status["step_name"] = "正在同步订阅..."
            cls._scan_status["total_items"] = 0
            cls._scan_status["current_item"] = 0

            if nf_service:
                logger.info("扫描 Step 3/3: 同步订阅")
                orchestrator = OrchestratorService(nf_service, mp_service)
                sync_results = await orchestrator.sync_subscriptions(db)
                cls._scan_status["total_items"] = len(sync_results)
                cls._scan_status["current_item"] = len(sync_results)
            else:
                logger.info("扫描 Step 3/3 跳过: NextFind 未配置")

            cls._scan_status["progress"] = 100
            cls._scan_status["current_step"] = 3
            cls._scan_status["step_name"] = "扫描完成"
            logger.info("Emby 全量扫描完成")

        except Exception as e:
            cls._scan_status["error"] = str(e)
            logger.error(f"Emby 扫描异常: {e}")
        finally:
            cls._scan_status["running"] = False

    @classmethod
    async def run_light_scan(
        cls,
        db,
        emby: EmbyService,
        tmdb: TMDBService,
    ):
        """轻量快速扫描 — 只刷新 Emby 缓存 + 补充缺失 TMDB 数据。

        用于 10 分钟间隔的定时刷新，不做全量 TMDB 查询也不同步订阅。

        Args:
            db: 数据库会话
            emby: Emby 服务实例
            tmdb: TMDB 服务实例
        """
        if cls._scan_status["running"]:
            logger.debug("轻量扫描跳过: 全量扫描正在运行中")
            return

        cls._scan_status["running"] = True
        cls._scan_status["progress"] = 0
        cls._scan_status["error"] = None
        cls._scan_status["started_at"] = datetime.now(UTC).isoformat()

        try:
            # Step 1: Sync Emby cache (0-70%)
            cls._scan_status["current_step"] = 1
            cls._scan_status["step_name"] = "正在快速刷新 Emby 缓存..."
            cls._scan_status["total_items"] = 0
            cls._scan_status["current_item"] = 0
            logger.info("轻量扫描 Step 1/2: 同步 Emby 缓存")
            sync_result = await emby.sync_cache(db)

            cls._scan_status["progress"] = 70
            logger.info(f"轻量扫描 Step 1/2 完成: {sync_result}")

            # Step 2: Supplement missing TMDB data (70-100%)
            cls._scan_status["current_step"] = 2
            cls._scan_status["step_name"] = "正在补充缺失 TMDB 数据..."
            cls._scan_status["total_items"] = 0
            cls._scan_status["current_item"] = 0

            logger.info("轻量扫描 Step 2/2: 补充缺失 TMDB 数据")
            tmdb_result = await emby.update_tmdb_data_missing(db, tmdb)

            cls._scan_status["progress"] = 100
            cls._scan_status["current_step"] = 2
            cls._scan_status["step_name"] = "轻量扫描完成"
            logger.info(f"轻量扫描 Step 2/2 完成: {tmdb_result}")

        except Exception as e:
            cls._scan_status["error"] = str(e)
            logger.error(f"轻量扫描异常: {e}")
        finally:
            cls._scan_status["running"] = False
