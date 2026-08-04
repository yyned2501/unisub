"""编排服务 — 协调 NextFind 和 MoviePilot 的订阅与同步逻辑。

订阅 = 本地记录 + NextFind 添加（+ MoviePilot 镜像，见 mp_sync）
取消 = NextFind 移除 + MoviePilot 清理 + 本地清理
同步 = NF 双向同步（nf_sync）+ MP 进度回写（mp_sync）
补充 = 对缺集条目调用 MoviePilot 搜索

本模块是薄编排层：NF 同步委托 NfSyncEngine，MP 订阅委托 MpSyncEngine，
自身只保留订阅 CRUD 与 TMDB/MP 补充逻辑。
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import UpstreamError
from app.core.logger import init_logger
from app.models.activity_log import ActivityLog
from app.models.subscription import Subscription
from app.models.tmdb_cache import TmdbCache
from app.schemas.subscription import SubscriptionResponse, SubscriptionSyncResult
from app.services.moviepilot import MoviePilotService
from app.services.mp_sync import MpSyncEngine
from app.services.nextfind import NextFindService
from app.services.nf_sync import NfSyncEngine
from app.services.tmdb import TMDBService

logger = init_logger()


class OrchestratorService:
    """编排服务 — 统一管理订阅、取消、同步与 MP 补充操作。"""

    def __init__(
        self,
        nf_service: NextFindService,
        mp_service: MoviePilotService | None = None,
        tmdb_service: TMDBService | None = None,
    ):
        """初始化编排服务。

        Args:
            nf_service: NextFind 服务实例
            mp_service: MoviePilot 服务实例（可选，MP 镜像订阅/补充搜索时需要）
            tmdb_service: TMDB 服务实例（可选，用于推断媒体类型）
        """
        self.nf = nf_service
        self.mp = mp_service
        self.tmdb = tmdb_service
        self._nf_sync = NfSyncEngine(nf_service)
        self._mp_sync = MpSyncEngine(mp_service, tmdb_service) if mp_service else None

    async def subscribe(
        self,
        db: AsyncSession,
        tmdb_id: int,
        title: str,
        media_type: str,
        poster_url: str | None = None,
        year: int | None = None,
        source: str | None = None,
    ) -> SubscriptionResponse:
        """创建订阅 — 先写本地库，通知 NextFind 添加，再镜像到 MoviePilot。

        MP 镜像为 best-effort：失败仅记日志，不回滚 NF 订阅。

        Args:
            db: 数据库会话
            tmdb_id: TMDB ID
            title: 媒体标题
            media_type: 媒体类型（movie / tv）
            poster_url: 海报 URL
            year: 发行年份
            source: 数据来源（manual / forward / auto_subscribe）

        Returns:
            新创建的订阅响应对象
        """
        # 检查是否已存在
        existing = await db.execute(select(Subscription).where(Subscription.tmdb_id == tmdb_id))
        existing = existing.scalar_one_or_none()
        if existing:
            logger.info("订阅已存在: %s (tmdb_id=%d)", title, tmdb_id)
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
            source=source or "manual",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(sub)

        # 通知 NextFind 添加订阅
        nf_result = await self.nf.add_subscription(tmdb_id, media_type=media_type, title=title)
        if "error" not in nf_result:
            sub.nf_subscribed = True
            nf_id = nf_result.get("id") or nf_result.get("sub_id") or ""
            sub.nf_sub_id = str(nf_id) if nf_id else None
            logger.info("NextFind 订阅成功: %s (%s, tmdb_id=%d)", title, media_type, tmdb_id)
        else:
            logger.error("NextFind 订阅失败: %s (%s, tmdb_id=%d), %s", title, media_type, tmdb_id, nf_result)
            await db.rollback()
            raise UpstreamError(f"NextFind 订阅失败: {nf_result.get('detail', nf_result.get('error', '未知错误'))}")

        # 记录活动日志
        log_entry = ActivityLog(
            id=str(uuid.uuid4()),
            action="subscribe",
            tmdb_id=tmdb_id,
            message=f"订阅了 {title} ({media_type})",
            created_at=datetime.now(UTC),
        )
        db.add(log_entry)

        # 镜像到 MoviePilot（best-effort，失败不阻塞 NF 订阅）
        if self._mp_sync:
            await self._mp_sync.subscribe(db, sub)

        await db.commit()
        await db.refresh(sub)

        return SubscriptionResponse.model_validate(sub)

    async def unsubscribe(self, db: AsyncSession, subscription_id: str) -> dict:
        """取消订阅 — 从 NextFind 移除，清理 MoviePilot 订阅，删除本地记录。

        如果 NextFind 移除失败，保留本地记录，避免同步时重新创建。

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
        nf_result = await self.nf.remove_subscription(sub.tmdb_id, media_type=sub.media_type)
        if "error" in nf_result:
            logger.warning("NextFind 取消订阅失败: %s, %s", sub.title, nf_result)
            # NF 移除失败，保留本地记录，避免同步时重新创建
            return {"success": False, "message": f"NextFind 取消订阅失败: {sub.title}"}

        # 记录活动日志
        log_entry = ActivityLog(
            id=str(uuid.uuid4()),
            action="unsubscribe",
            tmdb_id=sub.tmdb_id,
            message=f"取消订阅 {sub.title}",
            created_at=datetime.now(UTC),
        )
        db.add(log_entry)

        # 清理 MoviePilot 订阅（best-effort，在删除本地记录前处理子表行）
        if self._mp_sync:
            await self._mp_sync.unsubscribe(db, sub)

        # 删除本地记录
        await db.delete(sub)
        await db.commit()

        return {"success": True, "message": f"已取消订阅 {sub.title}"}

    async def sync_subscriptions(self, db: AsyncSession) -> list[SubscriptionSyncResult]:
        """同步订阅 — NF 双向同步 + MP 进度回写。

        Args:
            db: 数据库会话

        Returns:
            NF 同步的每条操作结果列表
        """
        results = await self._nf_sync.sync(db)
        if self._mp_sync:
            await self._mp_sync.sync(db)
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
                message=(f"MP 补充搜索: {sub.title} ({sub.media_type}), 缺集 {sub.nf_missing_eps}"),
                created_at=datetime.now(UTC),
            )
            db.add(log_entry)

        await db.commit()
        logger.info(f"MP 补充搜索完成: 处理了 {len(results)} 条缺集订阅")
        return results

    async def sync_tmdb_from_nf(self, db: AsyncSession) -> dict:
        """通过 NF 订阅数据判断哪些剧集需要刷新 TMDB 缓存。

        NF 的 total_episodes 变了 → TMDB 有新数据 → 只刷新这一条。
        避免批量全量扫描，减少 TMDB API 调用。

        Args:
            db: 数据库会话

        Returns:
            更新统计字典 {updated, skipped}
        """
        if not self.tmdb:
            logger.warning("TMDB 增量刷新跳过: TMDB 服务未配置")
            return {"updated": 0, "skipped": 0}

        nf_subs = await self.nf.get_subscriptions()
        tv_subs = [s for s in nf_subs if s.get("media_type") in ("tv", "剧集")]

        updated = 0
        skipped = 0
        for nf_sub in tv_subs:
            tid = int(nf_sub["tmdb_id"])
            nf_total = int(nf_sub.get("total_episodes") or 0)
            if nf_total <= 0:
                skipped += 1
                continue

            # 查询本地 tmdb_cache
            tc = await db.get(TmdbCache, tid)
            local_total = tc.tmdb_total_eps if tc else None

            # 一致 → 跳过
            if local_total == nf_total:
                skipped += 1
                continue

            # 不一致 → 调 TMDB API 刷新（用 update_cache_for_tv 自动写入缓存）
            if await self.tmdb.update_cache_for_tv(db, tid):
                updated += 1
            else:
                skipped += 1

        await db.commit()
        logger.info(f"TMDB 增量刷新: {updated} 条更新, {skipped} 条跳过")
        return {"updated": updated, "skipped": skipped}
