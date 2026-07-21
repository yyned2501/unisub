"""自动订阅应用服务。"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import init_logger
from app.models.activity_log import ActivityLog
from app.services import get_nf_service, get_tmdb_service
from app.services.auto_subscribe.config_store import get_config_store
from app.services.auto_subscribe.pipeline import run as run_pipeline

logger = init_logger(__name__)


class AutoSubscribeService:
    """编排自动订阅的配置、执行状态和运行历史。"""

    def __init__(self) -> None:
        """初始化互斥锁，阻止手动与定时运行重叠。"""
        self._run_lock = asyncio.Lock()
        self._running = False
        self._last_error: str | None = None

    def get_status(self) -> dict[str, Any]:
        """获取当前自动订阅运行状态。"""
        return {"running": self._running, "last_error": self._last_error}

    def get_config_response(self) -> dict[str, Any]:
        """获取配置、历史摘要与运行状态。"""
        store = get_config_store()
        config = store.load_config()
        history = store.load_history()
        enabled_sources = [name for name in ("douban", "mikan", "maoyan") if config.get(f"{name}_enabled")]
        return {
            "config": config,
            "last_run": history.get("last_run"),
            "last_stats": history.get("last_stats"),
            "enabled_sources": enabled_sources,
            **self.get_status(),
        }

    def save_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """保存经过迁移和 cron 校验的自动订阅配置。"""
        return get_config_store().save_config(config)

    def get_history(self) -> dict[str, Any]:
        """返回自动订阅历史。"""
        return get_config_store().load_history()

    def clear_history(self) -> None:
        """清空自动订阅历史与缓存。"""
        get_config_store().clear_history()

    async def run(self, db: AsyncSession, trigger: str = "manual") -> dict[str, Any]:
        """使用同一执行入口运行手动或定时自动订阅。"""
        if self._run_lock.locked():
            return {"success": False, "started": False, "message": "自动订阅正在运行"}

        async with self._run_lock:
            self._running = True
            self._last_error = None
            try:
                nf = await get_nf_service(db)
                if not nf:
                    return {"success": False, "started": False, "message": "NextFind 未配置或未启用"}

                tmdb = await get_tmdb_service(db)
                store = get_config_store()
                config = store.load_config()
                history = store.load_history()
                result = await run_pipeline(
                    config,
                    db,
                    nf,
                    tmdb_service=tmdb,
                    handled=history.get("handled", {}),
                    nf_cache=history.get("nf_cache", {}),
                )
                history.update(
                    {
                        "handled": result["handled"],
                        "nf_cache": result.get("nf_cache", {}),
                        "last_run": datetime.now(UTC).isoformat(),
                        "last_stats": _summarize_stats(result["stats"]),
                        "last_error": result["errors"] or None,
                    }
                )
                store.save_history(history)

                added = len(result["added"])
                error_count = len(result["errors"])
                message = f"自动订阅完成: 新增 {added} 条订阅"
                if error_count:
                    message += f"，{error_count} 个源抓取失败"
                db.add(
                    ActivityLog(
                        id=str(uuid.uuid4()),
                        action="system",
                        tmdb_id=None,
                        message=message,
                        created_at=datetime.now(UTC),
                    )
                )
                await db.commit()
                logger.info("[%s] %s", trigger, message)
                return {"success": True, "started": True, "message": message, "errors": result["errors"]}
            except Exception as exc:
                await db.rollback()
                self._last_error = str(exc)
                logger.exception("自动订阅运行异常: trigger=%s", trigger)
                return {"success": False, "started": False, "message": f"自动订阅运行失败: {exc}"}
            finally:
                self._running = False


def _summarize_stats(stats: dict[str, dict[str, int]]) -> dict[str, int]:
    """将每个来源的状态计数聚合为总计数。"""
    result: dict[str, int] = {}
    for source_stats in stats.values():
        for key, value in source_stats.items():
            result[key] = result.get(key, 0) + value
    return result


_service = AutoSubscribeService()


def get_auto_subscribe_service() -> AutoSubscribeService:
    """获取自动订阅应用服务单例。"""
    return _service
