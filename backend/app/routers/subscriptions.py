"""订阅管理路由 — 订阅列表、创建、取消、同步。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import init_logger
from app.models.subscription import Subscription
from app.schemas.subscription import (
    SubscriptionCreate,
    SubscriptionResponse,
    SubscriptionSyncResult,
)
from app.services import get_mp_service, get_nf_service
from app.services.orchestrator import OrchestratorService

router = APIRouter(prefix="/api/subscriptions", tags=["订阅管理"])
logger = init_logger()


@router.get("", response_model=list[SubscriptionResponse])
async def list_subscriptions(db: AsyncSession = Depends(get_db)):
    """获取所有订阅列表。"""
    result = await db.execute(
        select(Subscription).order_by(Subscription.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=SubscriptionResponse, status_code=201)
async def create_subscription(
    body: SubscriptionCreate, db: AsyncSession = Depends(get_db)
):
    """添加订阅 — 创建本地记录并通过 NextFind 添加订阅。"""
    nf = await get_nf_service(db)
    if not nf:
        raise HTTPException(status_code=503, detail="NextFind 平台未配置或未启用")

    orchestrator = OrchestratorService(nf)
    result = await orchestrator.subscribe(
        db=db,
        tmdb_id=body.tmdb_id,
        title=body.title,
        media_type=body.media_type,
        poster_url=body.poster_url,
        year=body.year,
    )
    return result


@router.delete("/{subscription_id}")
async def delete_subscription(
    subscription_id: str, db: AsyncSession = Depends(get_db)
):
    """取消订阅 — 从 NextFind 移除并删除本地记录。"""
    nf = await get_nf_service(db)
    if not nf:
        raise HTTPException(status_code=503, detail="NextFind 平台未配置或未启用")

    orchestrator = OrchestratorService(nf)
    result = await orchestrator.unsubscribe(db, subscription_id)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@router.get("/{subscription_id}", response_model=SubscriptionResponse)
async def get_subscription(
    subscription_id: str, db: AsyncSession = Depends(get_db)
):
    """获取单条订阅详情。"""
    sub = await db.get(Subscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="订阅记录不存在")
    return sub


@router.post("/sync", response_model=list[SubscriptionSyncResult])
async def sync_subscriptions(db: AsyncSession = Depends(get_db)):
    """手动同步 NextFind 订阅状态到本地数据库。"""
    nf = await get_nf_service(db)
    if not nf:
        raise HTTPException(status_code=503, detail="NextFind 平台未配置或未启用")

    orchestrator = OrchestratorService(nf)
    results = await orchestrator.sync_subscriptions(db)
    logger.info(f"手动同步完成: {len(results)} 条记录")
    return results
