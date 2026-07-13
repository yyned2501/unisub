"""编排服务 — 协调 NextFind 和 MoviePilot 的订阅与同步逻辑。

订阅 = 本地记录 + NextFind 添加
取消 = NextFind 移除 + 本地清理
同步 = 拉取 NF 状态 → 更新本地缺集信息
补充 = 对缺集条目调用 MoviePilot 搜索
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import init_logger
from app.models.activity_log import ActivityLog
from app.models.subscription import Subscription
from app.schemas.subscription import SubscriptionResponse, SubscriptionSyncResult
from app.services.moviepilot import MoviePilotService
from app.services.nextfind import NextFindService

logger = init_logger()


class OrchestratorService:
    """编排服务 — 统一管理订阅、取消、同步与 MP 补充操作。"""

    def __init__(
        self,
        nf_service: NextFindService,
        mp_service: MoviePilotService | None = None,
    ):
        """初始化编排服务。

        Args:
            nf_service: NextFind 服务实例
            mp_service: MoviePilot 服务实例（可选，仅补充搜索时需要）
        """
        self.nf = nf_service
        self.mp = mp_service

    async def subscribe(
        self,
        db: AsyncSession,
        tmdb_id: int,
        title: str,
        media_type: str,
        poster_url: str | None = None,
        year: int | None = None,
    ) -> SubscriptionResponse:
        """创建订阅 — 先写本地库，再通知 NextFind 添加。

        Args:
            db: 数据库会话
            tmdb_id: TMDB ID
            title: 媒体标题
            media_type: 媒体类型（movie / tv）
            poster_url: 海报 URL
            year: 发行年份

        Returns:
            新创建的订阅响应对象
        """
        # 检查是否已存在
        existing = await db.execute(
            select(Subscription).where(Subscription.tmdb_id == tmdb_id)
        )
        existing = existing.scalar_one_or_none()
        if existing:
            logger.info(f"订阅已存在: {title} (tmdb_id={tmdb_id})")
            return SubscriptionResponse.model_validate(existing)

        # 创建本地记录
        sub = Subscription(
            id=str(uuid.uuid4()),
            tmdb_id=tmdb_id,
            media_type=media_type,
            title=title,
            poster_url=poster_url,
            year=year,
            nf_subscribed=False,
            nf_status=None,
            nf_missing_eps=0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(sub)

        # 通知 NextFind 添加订阅
        nf_result = await self.nf.add_subscription(tmdb_id)
        if "error" not in nf_result:
            sub.nf_subscribed = True
            nf_id = nf_result.get("id") or nf_result.get("sub_id") or ""
            sub.nf_sub_id = str(nf_id) if nf_id else None
            logger.info(f"NextFind 订阅成功: {title} (tmdb_id={tmdb_id})")
        else:
            logger.warning(
                f"NextFind 订阅失败: {title} (tmdb_id={tmdb_id}), {nf_result}"
            )

        # 记录活动日志
        log_entry = ActivityLog(
            id=str(uuid.uuid4()),
            action="subscribe",
            tmdb_id=tmdb_id,
            message=f"订阅了 {title} ({media_type})",
            created_at=datetime.now(timezone.utc),
        )
        db.add(log_entry)

        await db.commit()
        await db.refresh(sub)

        return SubscriptionResponse.model_validate(sub)

    async def unsubscribe(self, db: AsyncSession, subscription_id: str) -> dict:
        """取消订阅 — 从 NextFind 移除，删除本地记录。

        Args:
            db: 数据库会话
            subscription_id: 订阅记录 UUID

        Returns:
            包含 success 和 message 的操作结果字典
        """
        sub = await db.get(Subscription, subscription_id)
        if not sub:
            return {"success": False, "message": "订阅记录不存在"}

        # 从 NextFind 移除
        nf_result = await self.nf.remove_subscription(sub.tmdb_id)
        if "error" in nf_result:
            logger.warning(f"NextFind 取消订阅失败: {sub.title}, {nf_result}")

        # 记录活动日志
        log_entry = ActivityLog(
            id=str(uuid.uuid4()),
            action="unsubscribe",
            tmdb_id=sub.tmdb_id,
            message=f"取消订阅 {sub.title}",
            created_at=datetime.now(timezone.utc),
        )
        db.add(log_entry)

        # 删除本地记录
        await db.delete(sub)
        await db.commit()

        return {"success": True, "message": f"已取消订阅 {sub.title}"}

    async def sync_subscriptions(
        self, db: AsyncSession
    ) -> list[SubscriptionSyncResult]:
        """同步 NextFind 订阅状态到本地数据库。

        从 NextFind 拉取所有订阅，匹配本地记录并更新缺集状态。

        Args:
            db: 数据库会话

        Returns:
            每条匹配记录的同步结果列表
        """
        nf_subs = await self.nf.get_subscriptions()
        results: list[SubscriptionSyncResult] = []

        for nf_sub in nf_subs:
            tmdb_id = nf_sub.get("tmdb_id")
            if not tmdb_id:
                continue

            # 查找本地记录
            stmt = select(Subscription).where(Subscription.tmdb_id == int(tmdb_id))
            local_sub = (await db.execute(stmt)).scalar_one_or_none()

            if not local_sub:
                continue

            # 更新 NextFind 状态字段
            nf_status = nf_sub.get("status") or nf_sub.get("nf_status")
            nf_missing = nf_sub.get("missing_eps") or nf_sub.get(
                "fillable_episodes_count", 0
            )

            local_sub.nf_status = str(nf_status) if nf_status else None
            local_sub.nf_missing_eps = int(nf_missing) if nf_missing else 0
            local_sub.updated_at = datetime.now(timezone.utc)

            needs_mp = local_sub.nf_missing_eps > 0

            result = SubscriptionSyncResult(
                tmdb_id=int(tmdb_id),
                title=local_sub.title,
                nf_status=local_sub.nf_status,
                nf_missing_eps=local_sub.nf_missing_eps,
                needs_mp_search=needs_mp,
                message=(
                    f"已同步: {local_sub.title}, 缺集 {local_sub.nf_missing_eps}"
                ),
            )
            results.append(result)

        # 记录同步活动
        log_entry = ActivityLog(
            id=str(uuid.uuid4()),
            action="sync",
            tmdb_id=None,
            message=f"同步完成: 更新了 {len(results)} 条订阅记录",
            created_at=datetime.now(timezone.utc),
        )
        db.add(log_entry)
        await db.commit()

        return results

    async def trigger_mp_supplement(self, db: AsyncSession) -> list[dict]:
        """触发 MoviePilot 补充搜索。

        查找所有缺集数 > 0 的活跃订阅，对每一项调用 MP 搜索 API。

        Args:
            db: 数据库会话

        Returns:
            MP 搜索结果列表，每项包含 tmdb_id、title、media_type 和 result
        """
        if not self.mp:
            logger.warning("MoviePilot 服务未配置，无法触发补充搜索")
            return [{"error": "MoviePilot 服务未配置"}]

        stmt = select(Subscription).where(
            Subscription.nf_missing_eps > 0,
            Subscription.completed == False,
        )
        subs = (await db.execute(stmt)).scalars().all()

        results: list[dict] = []
        for sub in subs:
            mp_result = await self.mp.search_media(sub.tmdb_id, sub.media_type)
            results.append(
                {
                    "tmdb_id": sub.tmdb_id,
                    "title": sub.title,
                    "media_type": sub.media_type,
                    "missing_eps": sub.nf_missing_eps,
                    "result": mp_result,
                }
            )

            # 记录活动日志
            log_entry = ActivityLog(
                id=str(uuid.uuid4()),
                action="mp_search",
                tmdb_id=sub.tmdb_id,
                message=(
                    f"MP 补充搜索: {sub.title} ({sub.media_type}), "
                    f"缺集 {sub.nf_missing_eps}"
                ),
                created_at=datetime.now(timezone.utc),
            )
            db.add(log_entry)

        await db.commit()
        logger.info(f"MP 补充搜索完成: 处理了 {len(results)} 条缺集订阅")
        return results
