"""定时任务路由 — 任务状态、手动触发、配置管理。"""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import init_logger
from app.models.activity_log import ActivityLog
from app.services import get_mp_service, get_nf_service
from app.services.orchestrator import OrchestratorService

router = APIRouter(prefix="/api/tasks", tags=["定时任务"])
logger = init_logger()

# 简单的内存任务状态与配置
_task_status: dict = {
    "last_run": None,
    "last_result": None,
    "running": False,
}

_task_config: dict = {
    "interval_minutes": 30,
    "mp_supplement_enabled": True,
    "auto_sync_enabled": True,
}


class TaskStatusResponse(BaseModel):
    """定时任务状态响应。"""

    running: bool
    last_run: str | None = None
    last_result: dict | None = None
    config: dict


class TaskConfigUpdate(BaseModel):
    """定时任务配置更新请求。"""

    interval_minutes: int | None = Field(None, ge=5, le=1440, description="轮询间隔（分钟）")
    mp_supplement_enabled: bool | None = Field(None, description="是否启用 MP 补充搜索")
    auto_sync_enabled: bool | None = Field(None, description="是否启用自动同步")


class TaskTriggerResponse(BaseModel):
    """手动触发任务响应。"""

    success: bool
    message: str
    sync_count: int = 0
    mp_search_count: int = 0


@router.get("/status", response_model=TaskStatusResponse)
async def get_task_status():
    """获取定时任务运行状态与配置。"""
    return TaskStatusResponse(
        running=_task_status["running"],
        last_run=_task_status["last_run"],
        last_result=_task_status["last_result"],
        config=_task_config,
    )


@router.post("/trigger", response_model=TaskTriggerResponse)
async def trigger_task(db: AsyncSession = Depends(get_db)):
    """手动触发一次完整的编排任务 — 同步 + MP 补充搜索。"""
    if _task_status["running"]:
        raise HTTPException(status_code=409, detail="已有任务正在运行中")

    _task_status["running"] = True
    sync_count = 0
    mp_search_count = 0

    try:
        nf = await get_nf_service(db)
        if not nf:
            return TaskTriggerResponse(
                success=False,
                message="NextFind 平台未配置或未启用",
            )

        mp = await get_mp_service(db)
        orchestrator = OrchestratorService(nf, mp)

        # 1. 同步订阅状态
        sync_results = await orchestrator.sync_subscriptions(db)
        sync_count = len(sync_results)

        # 2. 触发 MP 补充搜索（如果启用且有 MP 配置）
        if _task_config["mp_supplement_enabled"] and mp:
            mp_results = await orchestrator.trigger_mp_supplement(db)
            mp_search_count = len(mp_results)
        elif _task_config["mp_supplement_enabled"] and not mp:
            logger.info("MP 补充搜索跳过: MoviePilot 未配置")

        # 记录系统活动
        import uuid
        log_entry = ActivityLog(
            id=str(uuid.uuid4()),
            action="system",
            tmdb_id=None,
            message=(
                f"定时任务完成: 同步 {sync_count} 条, "
                f"MP 补充搜索 {mp_search_count} 条"
            ),
            created_at=datetime.now(timezone.utc),
        )
        db.add(log_entry)
        await db.commit()

        _task_status["last_run"] = datetime.now(timezone.utc).isoformat()
        _task_status["last_result"] = {
            "sync_count": sync_count,
            "mp_search_count": mp_search_count,
        }

        return TaskTriggerResponse(
            success=True,
            message="任务执行完成",
            sync_count=sync_count,
            mp_search_count=mp_search_count,
        )
    except Exception as e:
        logger.error(f"定时任务执行异常: {e}")
        return TaskTriggerResponse(
            success=False,
            message=f"任务执行失败: {str(e)}",
        )
    finally:
        _task_status["running"] = False


@router.put("/config", response_model=dict)
async def update_task_config(body: TaskConfigUpdate):
    """更新定时任务配置。"""
    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        _task_config[key] = value
    logger.info(f"任务配置已更新: {_task_config}")
    return {"success": True, "config": _task_config}
