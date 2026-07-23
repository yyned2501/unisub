"""自动订阅路由。"""

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
from app.schemas.auto_subscribe import (
    AutoSubConfigResponse,
    AutoSubConfigUpdate,
    AutoSubHistoryResponse,
    AutoSubMetaResponse,
    AutoSubRunResponse,
)
from app.services.auto_subscribe.models import SOURCE_NAMES, STATUS_LABELS
from app.services.auto_subscribe.service import get_auto_subscribe_service

router = APIRouter(prefix="/api/auto-subscribe", tags=["自动订阅"], dependencies=[Depends(get_current_user)])


@router.get("/config", response_model=AutoSubConfigResponse)
async def get_config() -> AutoSubConfigResponse:
    """获取自动订阅配置和运行状态。"""
    response = get_auto_subscribe_service().get_config_response()
    return AutoSubConfigResponse(
        **response,
        status_labels=STATUS_LABELS,
        source_names=SOURCE_NAMES,
    )


@router.put("/config", response_model=dict)
async def update_config(body: AutoSubConfigUpdate) -> dict:
    """更新自动订阅配置。"""
    try:
        config = get_auto_subscribe_service().save_config(body.config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "config": config}


@router.post("/run", response_model=AutoSubRunResponse)
async def trigger_run() -> AutoSubRunResponse:
    """手动触发一次自动订阅运行（后台执行，立即返回）。"""
    import asyncio

    from app.core.database import async_session

    svc = get_auto_subscribe_service()
    if svc.get_status()["running"]:
        return AutoSubRunResponse(success=False, started=False, message="自动订阅正在运行中")

    async def _background_run():
        async with async_session() as bg_db:
            result = await svc.run(bg_db, trigger="manual")
            if result.get("success"):
                from app.services import get_nf_service
                from app.services.orchestrator import OrchestratorService

                nf = await get_nf_service(bg_db)
                if nf:
                    orchestrator = OrchestratorService(nf)
                    await orchestrator.sync_subscriptions(bg_db)

    asyncio.create_task(_background_run())
    return AutoSubRunResponse(success=True, started=True, message="自动订阅已启动，正在后台运行")


@router.get("/history", response_model=AutoSubHistoryResponse)
async def get_history() -> AutoSubHistoryResponse:
    """获取自动订阅处理历史。"""
    history = get_auto_subscribe_service().get_history()
    items = [
        {
            "key": key,
            "status": value.get("status", ""),
            "time": value.get("time"),
            "tmdb_id": value.get("tmdb_id"),
            "media_type": value.get("media_type"),
        }
        for key, value in history.get("handled", {}).items()
    ]
    items.sort(key=lambda item: item.get("time") or "", reverse=True)
    return AutoSubHistoryResponse(
        items=items[:200],
        last_run=history.get("last_run"),
        stats=history.get("last_stats"),
    )


@router.delete("/history", response_model=dict)
async def clear_history() -> dict:
    """清空自动订阅处理历史。"""
    get_auto_subscribe_service().clear_history()
    return {"success": True, "cleared": True}


@router.get("/meta", response_model=AutoSubMetaResponse)
async def get_meta() -> AutoSubMetaResponse:
    """获取自动订阅前端元数据。"""
    from app.services.auto_subscribe import douban

    return AutoSubMetaResponse(
        douban_ranks=[{"value": key, "label": value["label"]} for key, value in douban.DOUBAN_RANKS.items()],
        maoyan_platforms=[
            {"value": "全网", "label": "全网"},
            {"value": "腾讯视频", "label": "腾讯视频"},
            {"value": "爱奇艺", "label": "爱奇艺"},
            {"value": "优酷", "label": "优酷"},
            {"value": "芒果TV", "label": "芒果TV"},
            {"value": "搜狐视频", "label": "搜狐视频"},
            {"value": "乐视", "label": "乐视"},
            {"value": "PPTV", "label": "PPTV"},
        ],
        maoyan_media_types=[
            {"value": "series", "label": "电视剧+网络剧"},
            {"value": "tv", "label": "电视剧"},
            {"value": "web", "label": "网络剧"},
            {"value": "variety", "label": "综艺"},
        ],
        seasons=[
            {"value": value, "label": label}
            for value, label in [("当前", "当前季"), ("春", "春季"), ("夏", "夏季"), ("秋", "秋季"), ("冬", "冬季")]
        ],
        source_names=SOURCE_NAMES,
        status_labels=STATUS_LABELS,
    )
