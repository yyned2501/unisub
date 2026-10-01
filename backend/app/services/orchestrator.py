"""编排服务 — 协调 NextFind 和 MoviePilot 的订阅与同步逻辑。

订阅 = 本地记录（权威）+ NextFind 推送 + MoviePilot 镜像
取消 = NextFind 移除 + MoviePilot 清理 + 本地清理
同步 = NF 双向同步（nf_sync）+ MP 进度回写（mp_sync）
补充 = 对缺集条目调用 MoviePilot 搜索

契约（2026-10-01 变更，语义见 subscribe 文档）：
用户请求路径只等「本地落库 + commit」，NF 建订阅与 MP 镜像丢到后台任务
（schedule_upstream）。上游失败不回滚本地订阅；NfSyncEngine Phase 2 与
MpSyncEngine.sync 每轮同步都会补上缺失的上游订阅，最终一致。

本模块是薄编排层：NF 同步委托 NfSyncEngine，MP 订阅委托 MpSyncEngine，
自身只保留订阅 CRUD、上游推送编排与 TMDB/MP 补充逻辑。
"""

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import async_session
from app.core.logger import init_logger
from app.models.subscription import Subscription
from app.models.tmdb_cache import TmdbCache
from app.schemas.subscription import SubscriptionResponse, SubscriptionSyncResult
from app.services.activity import log_activity
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
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ):
        """初始化编排服务。

        Args:
            nf_service: NextFind 服务实例
            mp_service: MoviePilot 服务实例（可选，MP 镜像订阅/补充搜索时需要）
            tmdb_service: TMDB 服务实例（可选，MP 缺集计算与 TMDB 缓存同步用）
            session_factory: 后台任务自建会话用的工厂（默认 app.core.database.async_session；
                测试可注入内存库工厂）
        """
        self.nf = nf_service
        self.mp = mp_service
        self.tmdb = tmdb_service
        self._nf_sync = NfSyncEngine(nf_service)
        self._mp_sync = MpSyncEngine(mp_service, tmdb_service) if mp_service else None
        self._session_factory = session_factory or async_session
        self._upstream_tasks: set[asyncio.Task] = set()

    def schedule_upstream(self, sub_id: str) -> None:
        """把「推送 NF + 镜像 MP」排到事件循环后台执行，不阻塞调用方。

        任务内部自建数据库会话、自行吞掉异常（本地订阅是权威记录，上游失败
        只记日志 + 活动日志，由同步引擎兜底重试）。

        Args:
            sub_id: 本地订阅 UUID
        """
        try:
            task = asyncio.create_task(self._upstream_task(sub_id))
        except RuntimeError:  # 无运行中的事件循环：退化处理，交给同步引擎兜底
            logger.warning("上游订阅同步 — 无事件循环，改由同步引擎兜底: %s", sub_id)
            return
        self._upstream_tasks.add(task)
        task.add_done_callback(self._upstream_tasks.discard)

    async def _upstream_task(self, sub_id: str) -> None:
        """后台任务入口 — 任何异常都不得逃逸到事件循环。"""
        try:
            await self.sync_upstream(sub_id)
        except Exception as e:  # noqa: BLE001 — 后台任务必须自吞，否则只是噪音
            logger.error(
                "上游订阅同步异常（本地订阅不受影响）: %s, %s: %s",
                sub_id,
                type(e).__name__,
                e,
            )

    async def drain_upstream(self) -> list[Exception]:
        """等待所有在飞的上游任务结束，返回其中抛出的异常（测试/优雅停机用）。"""
        errors: list[Exception] = []
        while self._upstream_tasks:
            done = await asyncio.gather(*list(self._upstream_tasks), return_exceptions=True)
            errors.extend(item for item in done if isinstance(item, Exception))
        return errors

    async def sync_upstream(self, sub_id: str, db: AsyncSession | None = None) -> dict[str, bool]:
        """把本地订阅推送到 NextFind 并镜像到 MoviePilot（best-effort）。

        Args:
            sub_id: 本地订阅 UUID
            db: 复用调用方会话（内联模式）；为 None 时自建会话（后台任务模式）

        Returns:
            ``{"nf": 是否推送成功, "mp": 是否镜像成功}``
        """
        if db is not None:
            return await self._sync_upstream_inner(db, sub_id)
        async with self._session_factory() as own:
            return await self._sync_upstream_inner(own, sub_id)

    async def _sync_upstream_inner(self, db: AsyncSession, sub_id: str) -> dict[str, bool]:
        """上游推送实现 — NF 添加 + MP 镜像，各自失败互不牵连。"""
        result = {"nf": False, "mp": False}
        sub = await db.get(Subscription, sub_id)
        if sub is None:
            logger.warning("上游订阅同步 — 本地记录已不存在，跳过: %s", sub_id)
            return result

        # 通知 NextFind 添加订阅（失败不回滚本地记录）
        nf_result = await self.nf.add_subscription(sub.tmdb_id, media_type=sub.media_type, title=sub.title)
        if "error" not in nf_result:
            sub.nf_subscribed = True
            nf_id = nf_result.get("id") or nf_result.get("sub_id") or ""
            sub.nf_sub_id = str(nf_id) if nf_id else None
            sub.updated_at = datetime.now(UTC)
            result["nf"] = True
            logger.info("NextFind 订阅成功: %s (%s, tmdb_id=%d)", sub.title, sub.media_type, sub.tmdb_id)
        else:
            logger.error(
                "NextFind 订阅失败（本地保留，待同步引擎重试）: %s (%s, tmdb_id=%d), %s",
                sub.title,
                sub.media_type,
                sub.tmdb_id,
                nf_result,
            )
            await log_activity(
                db,
                "subscribe",
                f"NF 订阅待重试: {sub.title} ({sub.media_type})",
                tmdb_id=sub.tmdb_id,
            )

        # 镜像到 MoviePilot（best-effort，失败不阻塞 NF 订阅）
        # 用 SAVEPOINT 把镜像写入隔离：镜像自己失败时只回滚镜像这一段，
        # 不得把本地订阅/活动日志一起回滚（MpSyncEngine 的契约就是这么写的：
        # "失败仅记日志，不回滚 NF 订阅"）。
        if self._mp_sync:
            try:
                async with db.begin_nested():
                    await self._mp_sync.subscribe(db, sub)
                result["mp"] = True
            except Exception as e:  # 镜像失败不得影响用户订阅
                logger.error(
                    "MP 镜像失败（订阅已保留）: %s (tmdb_id=%d), %s: %s",
                    sub.title,
                    sub.tmdb_id,
                    type(e).__name__,
                    e,
                )

        await db.commit()
        return result

    async def subscribe(
        self,
        db: AsyncSession,
        tmdb_id: int,
        title: str,
        media_type: str,
        poster_url: str | None = None,
        year: int | None = None,
        source: str | None = None,
        defer_upstream: bool = True,
    ) -> SubscriptionResponse:
        """创建订阅 — 本地先落库并立即返回，NF/MP 推送不阻塞请求。

        契约（2026-10-01 变更）：
        - 本地记录是权威事实：用户请求只等本地 commit（毫秒级），不再等
          NF 建订阅（~1s）和 MP 镜像（实测 12~13s）。
        - defer_upstream=True（默认）：NF 推送 + MP 镜像交给后台任务；上游失败
          不回滚本地订阅，NfSyncEngine Phase 2 / MpSyncEngine.sync 兜底重试。
        - defer_upstream=False：在调用方会话内联执行上游推送（测试或需要确定性
          返回 nf_subscribed 的调用方）。
        - 并发重复提交由唯一索引兜底：撞索引时返回已存在记录，不再抛错。

        Args:
            db: 数据库会话
            tmdb_id: TMDB ID
            title: 媒体标题
            media_type: 媒体类型（movie / tv）
            poster_url: 海报 URL
            year: 发行年份
            source: 数据来源（manual / forward / auto_subscribe）
            defer_upstream: 是否把 NF/MP 上游推送丢到后台（默认 True）

        Returns:
            新创建的订阅响应对象（defer_upstream=True 时 nf_subscribed 初值为 False，
            表示上游待同步）
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

        # 显式 flush：父行必须先于 mp_subscription 子行落库。
        # Subscription 与 MpSubscription 之间只有裸 FK 列、没有 relationship()，
        # SQLAlchemy 的工作单元只按关系排序 INSERT、不按 FK 排序。电影分支
        # （MpSyncEngine.subscribe → _create_mp_sub 全程无 DB 查询）没有 autoflush
        # 的机会，commit 时子表 INSERT 会先发出 → 撞 FK 违例（2026-10-01 生产事故）。
        #
        # 唯一索引兜底：并发重复提交（同一 tmdb_id 两个请求）时，预检可能都看不到
        # 对方未提交的行，INSERT 会撞 ix_subscriptions_tmdb_id。此处捕获后返回已
        # 存在记录 —— 幂等，且不再把数据库异常抛给用户。
        try:
            await db.flush()
            # 记录活动日志
            await log_activity(db, "subscribe", f"订阅了 {title} ({media_type})", tmdb_id=tmdb_id)
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = (
                await db.execute(select(Subscription).where(Subscription.tmdb_id == tmdb_id))
            ).scalar_one_or_none()
            if existing is None:
                raise
            logger.info("订阅并发重复，返回已存在记录: %s (tmdb_id=%d)", title, tmdb_id)
            return SubscriptionResponse.model_validate(existing)

        await db.refresh(sub)

        if defer_upstream:
            self.schedule_upstream(sub.id)
        else:
            await self.sync_upstream(sub.id, db=db)
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
        await log_activity(db, "unsubscribe", f"取消订阅 {sub.title}", tmdb_id=sub.tmdb_id)

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
            await log_activity(
                db,
                "mp_search",
                f"MP 补充搜索: {sub.title} ({sub.media_type}), 缺集 {sub.nf_missing_eps}",
                tmdb_id=sub.tmdb_id,
            )

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
