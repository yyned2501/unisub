"""上游推送 — 把本地订阅推到 NextFind 并镜像到 MoviePilot。

契约（2026-10-01，语义见 ``OrchestratorService.subscribe``）：
用户请求路径只等「本地落库 + commit」，NF 建订阅与 MP 镜像丢到后台任务。
上游失败不回滚本地订阅；NfSyncEngine Phase 2 与 MpSyncEngine.sync 每轮同步
都会补上缺失的上游订阅，最终一致。

契约（2026-10-02，S-B5 / docs/SPEC-CANCEL-RACE.md）：
后台任务在每个上游调用（NF 建订阅 / MP 镜像）前重查本地行 —— 取消 = 本地行没了。
行不存在 → 放弃后续上游动作并落 action="system" 可见日志，判定只读库。
事务边界也是契约（§8.3）：上游出网期间不得持有本地业务行的写锁 —— NF 写回后
立即 commit（A）；出网返回后再查一次本地行，行已删则撤销本任务刚建的那一条
上游订阅（B）。只记日志不算修好：上游残留 = 僵尸订阅，会继续下载。
"""

import asyncio
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from app.core.logger import init_logger
from app.models.subscription import Subscription
from app.services.activity import log_activity
from app.services.moviepilot import MoviePilotService
from app.services.mp_sync import MpSyncEngine
from app.services.nextfind import NextFindService

logger = init_logger()


class _UpstreamCancelledError(Exception):
    """内部信号：上游出网返回时本地订阅已被取消。

    只为借 ``async with db.begin_nested()`` 的自动回滚，把 MP 镜像那段子表写入丢掉；
    在 ``_sync_upstream_inner`` 内就地捕获，不外泄、不当作失败处理。
    """


class UpstreamPushMixin:
    """上游推送能力 — 由 ``OrchestratorService`` 组合，依赖其构造出的属性。

    取消判定与补偿在 ``orchestrator_cancel.CancelGuardMixin``。
    """

    nf: NextFindService
    mp: MoviePilotService | None
    _mp_sync: MpSyncEngine | None
    _session_factory: async_sessionmaker[AsyncSession]
    _upstream_tasks: set[asyncio.Task]

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
        """上游推送实现 — NF 添加 + MP 镜像，各自失败互不牵连。

        每个上游调用前重查本地行（只读库）：行不存在 = 用户已取消 → 放弃后续
        上游动作 + 落可见日志。判定不得用内存标记（重启即丢、多 worker 不共享）。

        事务边界（docs/SPEC-CANCEL-RACE.md §8.3）：
        - A：NF 写回后**立即 commit**。NF 调用是出网请求、MP 镜像是 12~15s 出网，
          只 commit 一次会把 subscriptions 行锁持有到镜像结束 —— 用户的 DELETE
          排不进锁，守卫读到的就是「锁窗前的快照」（守卫在、证据迟到 12s）。
        - B：上游调用**返回后**再查一次本地行，行已删 → 撤销本任务刚建的那一条
          上游订阅（NF/MP 各一次，精确有界）。上游残留 = 僵尸订阅，会继续下载。
        """
        result = {"nf": False, "mp": False}
        sub = await db.get(Subscription, sub_id)
        if sub is None:
            await self._skip_cancelled_upstream(db, sub_id)
            return result

        # 提前取出标量：取消路径会 rollback / 行已删，之后 sub 不再是可信来源
        title, media_type, tmdb_id = sub.title, sub.media_type, sub.tmdb_id

        # NF 建订阅前重查本地行
        if not await self._local_subscription_exists(db, sub_id):
            await self._skip_cancelled_upstream(db, sub_id, title=title, tmdb_id=tmdb_id)
            return result

        # 通知 NextFind 添加订阅（失败不回滚本地记录）
        nf_result = await self.nf.add_subscription(tmdb_id, media_type=media_type, title=title)
        nf_created = "error" not in nf_result

        # B（NF 侧）：NF 调用是出网请求（实测 ~1s），用户的取消常常正好落在这段窗口里
        # （生产僵尸订阅 mp_sub_id=2263：取消 +107ms，MP 建订阅在取消后 +15s）。
        # 返回时行已删 → 撤掉刚建的这条 NF 订阅，后续 MP 镜像不再执行。
        if not await self._local_subscription_exists(db, sub_id):
            await self._revoke_cancelled_upstream(
                db,
                sub_id,
                title=title,
                tmdb_id=tmdb_id,
                media_type=media_type,
                nf_created=nf_created,
                mp_sub_ids=[],
            )
            return result

        if nf_created:
            sub.nf_subscribed = True
            nf_id = nf_result.get("id") or nf_result.get("sub_id") or ""
            sub.nf_sub_id = str(nf_id) if nf_id else None
            sub.updated_at = datetime.now(UTC)
            result["nf"] = True
            logger.info("NextFind 订阅成功: %s (%s, tmdb_id=%d)", title, media_type, tmdb_id)
        else:
            logger.error(
                "NextFind 订阅失败（本地保留，待同步引擎重试）: %s (%s, tmdb_id=%d), %s",
                title,
                media_type,
                tmdb_id,
                nf_result,
            )
            await log_activity(
                db,
                "subscribe",
                f"NF 订阅待重试: {title} ({media_type})",
                tmdb_id=tmdb_id,
            )

        # A1：NF 写回后立即 commit（NF 已成功，写回是安全的）—— 行锁在这里就释放，
        # 不再持有到 MP 镜像出网（实测 12~15s）结束；否则用户的 DELETE 排不进锁，
        # 守卫读到的只是「锁窗前的快照」。写回瞬间若行已被并发 DELETE 干掉，flush 会
        # 因 0 行匹配抛 StaleDataError：那不是失败，是「取消赢了」→ 按取消处理。
        cancelled = False
        try:
            await db.commit()
        except StaleDataError:
            await db.rollback()
            cancelled = True

        # A2：MP 镜像前重查本地行 —— 此刻是新事务，READ COMMITTED 能看到刚提交的
        # DELETE（取消若被写回的行锁挡住，也在 A1 提交后立刻落库）。
        if cancelled or not await self._local_subscription_exists(db, sub_id):
            await self._revoke_cancelled_upstream(
                db,
                sub_id,
                title=title,
                tmdb_id=tmdb_id,
                media_type=media_type,
                nf_created=nf_created,
                mp_sub_ids=[],
            )
            return result

        # 镜像到 MoviePilot（best-effort，失败不阻塞 NF 订阅）
        # 用 SAVEPOINT 把镜像写入隔离：镜像自己失败时只回滚镜像这一段，
        # 不得把本地订阅/活动日志一起回滚（MpSyncEngine 的契约就是这么写的：
        # "失败仅记日志，不回滚 NF 订阅"）。
        # B（MP 侧）：镜像是 12~15s 出网，返回后复查本地行；行已删则回滚本段子表写入
        # （父行没了，插入子行会撞 FK）+ 撤掉刚建的那条 MP 订阅。
        if self._mp_sync:
            created: list[int] = []
            try:
                async with db.begin_nested():
                    created = await self._mp_sync.subscribe(db, sub)
                    if not await self._local_subscription_exists(db, sub_id):
                        raise _UpstreamCancelledError
                result["mp"] = True
            except _UpstreamCancelledError:
                # §8.3-B 写明「NF/MP 各撤一次」：取消路径自己也调过 NF remove，但本任务的
                # add 可能在那之后才被 NF 处理；补偿这次 remove 幂等无副作用
                # （真机复验：NF 取消后列表里留的是 status=cancelled 历史行，不是活跃订阅）。
                await self._revoke_cancelled_upstream(
                    db,
                    sub_id,
                    title=title,
                    tmdb_id=tmdb_id,
                    media_type=media_type,
                    nf_created=nf_created,
                    mp_sub_ids=created,
                )
                return result
            except Exception as e:  # 镜像失败不得影响用户订阅
                logger.error(
                    "MP 镜像失败（订阅已保留）: %s (tmdb_id=%d), %s: %s",
                    title,
                    tmdb_id,
                    type(e).__name__,
                    e,
                )

        await db.commit()
        return result
