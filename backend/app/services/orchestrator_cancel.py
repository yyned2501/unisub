"""取消竞态防护 — 「本地行还在吗」的判定与出网返回后的上游补偿。

契约见 docs/SPEC-CANCEL-RACE.md 与 ``orchestrator_upstream`` 模块说明：
- 判定只读库（``_local_subscription_exists``），不用内存标记 —— 重启即丢、
  多 worker 不共享；
- 上游出网返回时行已删 → 撤销本任务刚建的上游订阅（``_revoke_cancelled_upstream``），
  精确、有界、幂等。只记日志不算修好：上游残留 = 僵尸订阅，会继续下载。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import init_logger
from app.models.subscription import Subscription
from app.services.activity import log_activity
from app.services.moviepilot import MoviePilotService
from app.services.nextfind import NextFindService

logger = init_logger()


class CancelGuardMixin:
    """取消判定与补偿能力 — 由 ``OrchestratorService`` 组合，依赖其构造出的属性。"""

    nf: NextFindService
    mp: MoviePilotService | None

    async def _local_subscription_exists(self, db: AsyncSession, sub_id: str) -> bool:
        """重查本地订阅行是否仍存在 — 「取消」的唯一权威信号就是库里这行没了。

        用 ``no_autoflush``：本方法只问库、不触发未提交写回的 flush
        （行已被并发删除时 flush 会撞 StaleDataError，实测 UPDATE 0 行），
        也不让 identity map 缓存掩盖「行已删」的事实。

        Args:
            db: 数据库会话
            sub_id: 本地订阅 UUID

        Returns:
            True 表示行仍在（可继续上游动作），False 表示已被取消/删除
        """
        stmt = select(Subscription).where(Subscription.id == sub_id)
        with db.no_autoflush:
            return (await db.execute(stmt)).scalar_one_or_none() is not None

    async def _skip_cancelled_upstream(
        self, db: AsyncSession, sub_id: str, title: str | None = None, tmdb_id: int | None = None
    ) -> None:
        """本地订阅已被取消 — 放弃后续上游动作，并落一条可见记录（不静默跳过）。

        Args:
            db: 数据库会话
            sub_id: 本地订阅 UUID（行已删时只能用它标识）
            title: 订阅标题（行还在时已知；行已删时为 None）
            tmdb_id: TMDB ID（同上）
        """
        label = f": {title}" if title else f" (id={sub_id})"
        logger.warning("上游订阅同步 — 订阅已取消，跳过上游推送%s", label)
        await log_activity(db, "system", f"订阅已取消，跳过上游推送{label}", tmdb_id=tmdb_id)
        await db.commit()

    async def _revoke_cancelled_upstream(
        self,
        db: AsyncSession,
        sub_id: str,
        *,
        title: str,
        tmdb_id: int,
        media_type: str,
        nf_created: bool,
        mp_sub_ids: list[int],
    ) -> None:
        """出网返回时发现本地订阅已被取消 — 撤销本任务刚建的上游订阅（§8.3-B）。

        只撤本任务自己刚拿到的那些：NF 走 ``(tmdb_id, media_type)`` 的 remove 契约，
        MP 走 ``mp_sub_id`` —— 精确、有界、幂等，**不做全量上游对账**。只记可见日志
        不算修好：上游残留 = 僵尸订阅，会继续下载。

        Args:
            db: 数据库会话
            sub_id: 本地订阅 UUID（行已删，只能用它标识）
            title: 订阅标题
            tmdb_id: TMDB ID
            media_type: 媒体类型
            nf_created: 本次调用是否刚在 NF 建了订阅（建了才撤）
            mp_sub_ids: 本次镜像刚在 MP 新建的订阅 id（建了才撤）
        """
        revoked: list[str] = []
        if nf_created:
            result = await self.nf.remove_subscription(tmdb_id, media_type=media_type)
            if "error" in result:
                logger.error("上游窗口内已取消 — 撤销 NF 订阅失败: %s (tmdb_id=%d), %s", title, tmdb_id, result)
            else:
                revoked.append("NF")
                logger.warning("上游窗口内已取消 — 已撤销 NF 订阅: %s (tmdb_id=%d)", title, tmdb_id)

        for mp_sub_id in mp_sub_ids:
            if self.mp is None:  # 有 mp_sub_id 必然配了 MP，纯属类型收窄
                continue
            result = await self.mp.delete_subscription(mp_sub_id)
            if "error" in result:
                logger.error("上游窗口内已取消 — 撤销 MP 订阅失败: %s (mp_sub_id=%s), %s", title, mp_sub_id, result)
            else:
                revoked.append(f"MP:{mp_sub_id}")
                logger.warning("上游窗口内已取消 — 已撤销 MP 订阅: %s (mp_sub_id=%s)", title, mp_sub_id)

        suffix = f"，并撤销刚建的上游订阅（{'/'.join(revoked)}）" if revoked else ""
        await log_activity(
            db,
            "system",
            f"订阅已取消，跳过上游推送{suffix} — {title} (tmdb_id={tmdb_id})",
            tmdb_id=tmdb_id,
        )
        await db.commit()
