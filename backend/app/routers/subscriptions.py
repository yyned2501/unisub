"""订阅管理路由 — 订阅列表、创建、取消、同步。"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.logger import init_logger
from app.models.platform_config import PlatformConfig
from app.models.subscription import Subscription
from app.schemas.subscription import (
    SubscriptionCreate,
    SubscriptionResponse,
    SubscriptionSyncResult,
)
from app.services import get_tmdb_service, require_nf_service
from app.services.nextfind import NextFindService
from app.services.orchestrator import OrchestratorService
from app.services.subscription import (
    background_update_tmdb_cache,
    list_subscriptions_with_cache,
)

router = APIRouter(prefix="/api/subscriptions", tags=["订阅管理"], dependencies=[Depends(get_current_user)])
logger = init_logger()


@router.get("", response_model=list[SubscriptionResponse])
async def list_subscriptions(db: AsyncSession = Depends(get_db)):
    """获取所有订阅列表。"""
    # 获取 NextFind 基础 URL 用于补全相对路径海报
    nf_result = await db.execute(select(PlatformConfig).where(PlatformConfig.name == "nextfind"))
    nf_config = nf_result.scalar_one_or_none()
    nf_base_url = nf_config.base_url if nf_config else None

    subs = await list_subscriptions_with_cache(db, nf_base_url=nf_base_url)

    # 后台异步更新 TMDB 数据
    tmdb = await get_tmdb_service(db)
    if tmdb:
        tv_subs = [s for s in subs if s.media_type == "tv" and s.nf_missing_eps > 0]
        asyncio.create_task(background_update_tmdb_cache(tmdb, tv_subs))

    return subs


@router.post("", response_model=SubscriptionResponse, status_code=201)
async def create_subscription(
    body: SubscriptionCreate,
    db: AsyncSession = Depends(get_db),
    nf: NextFindService = Depends(require_nf_service),
):
    """添加订阅 — 创建本地记录并通过 NextFind 添加订阅。"""
    orchestrator = OrchestratorService(nf)
    return await orchestrator.subscribe(
        db=db,
        tmdb_id=body.tmdb_id,
        title=body.title,
        media_type=body.media_type,
        poster_url=body.poster_url,
        year=body.year,
    )


@router.delete("/{subscription_id}")
async def delete_subscription(
    subscription_id: str,
    db: AsyncSession = Depends(get_db),
    nf: NextFindService = Depends(require_nf_service),
):
    """取消订阅 — 从 NextFind 移除并删除本地记录。"""
    orchestrator = OrchestratorService(nf)
    result = await orchestrator.unsubscribe(db, subscription_id)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@router.patch("/{subscription_id}/blacklist")
async def toggle_blacklist(
    subscription_id: str,
    db: AsyncSession = Depends(get_db),
):
    """切换订阅黑名单状态。"""
    sub = await db.get(Subscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="订阅记录不存在")
    sub.blacklisted = not sub.blacklisted
    await db.commit()
    await db.refresh(sub)
    logger.info(f"{'拉黑' if sub.blacklisted else '解除拉黑'}: {sub.title} (tmdb_id={sub.tmdb_id})")
    return {
        "success": True,
        "blacklisted": sub.blacklisted,
        "message": f"已{'拉黑' if sub.blacklisted else '解除拉黑'}「{sub.title}」",
    }


@router.get("/{subscription_id}", response_model=SubscriptionResponse)
async def get_subscription(subscription_id: str, db: AsyncSession = Depends(get_db)):
    """获取单条订阅详情。"""
    sub = await db.get(Subscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="订阅记录不存在")
    return sub


@router.post("/sync", response_model=list[SubscriptionSyncResult])
async def sync_subscriptions(
    db: AsyncSession = Depends(get_db),
    nf: NextFindService = Depends(require_nf_service),
):
    """手动同步 NextFind 订阅状态到本地数据库。"""
    orchestrator = OrchestratorService(nf)
    results = await orchestrator.sync_subscriptions(db)
    logger.info(f"手动同步完成: {len(results)} 条记录")
    return results
