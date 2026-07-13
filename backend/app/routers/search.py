"""搜索路由 — 统一 TMDB 搜索入口，调用 NextFind OpenAPI。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import init_logger
from app.models.subscription import Subscription
from app.schemas.search import SearchResponse, SearchResultItem
from app.services import get_nf_service

router = APIRouter(prefix="/api/search", tags=["搜索"])
logger = init_logger()


@router.get("", response_model=SearchResponse)
async def search_media(
    q: str = Query(..., description="搜索关键词"),
    type: str = Query("all", description="媒体类型: movie / tv / all"),
    db: AsyncSession = Depends(get_db),
):
    """统一 TMDB 搜索 — 调用 NextFind OpenAPI 搜索接口。

    会自动标注每个搜索结果是否已被本地订阅。
    """
    nf = await get_nf_service(db)
    if not nf:
        raise HTTPException(status_code=503, detail="NextFind 平台未配置或未启用")

    # 获取已订阅的 tmdb_id 集合
    subscribed = await db.execute(select(Subscription.tmdb_id))
    subscribed_ids = {row[0] for row in subscribed.all()}

    # 调用 NextFind 搜索
    raw_results = await nf.search_tmdb(q, type)

    items: list[SearchResultItem] = []
    for item in raw_results:
        tmdb_id = item.get("tmdb_id") or item.get("id") or item.get("tmdbId", 0)
        items.append(
            SearchResultItem(
                tmdb_id=int(tmdb_id),
                title=item.get("title") or item.get("name", ""),
                media_type=item.get("media_type") or item.get("type", type),
                year=item.get("year") or item.get("release_date", "")[:4] if item.get("release_date") else None,
                poster_url=item.get("poster_url") or item.get("poster_path"),
                overview=item.get("overview"),
                is_subscribed=int(tmdb_id) in subscribed_ids,
            )
        )

    logger.info(f"搜索完成: q='{q}', type={type}, 结果 {len(items)} 条")
    return SearchResponse(total=len(items), items=items)
