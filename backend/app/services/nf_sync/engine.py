"""NextFind 双向同步引擎。

从 orchestrator 拆出的 NF ↔ 本地数据库双向同步入口。以本地数据库为准，
确保 NextFind 与本地订阅状态一致。各阶段的具体实现见 ``phases/``。

阶段职责一览（详见各阶段函数）：
    Phase 0   清理 NF 中元数据异常的活跃订阅
    Phase 1   NF → 本地：更新状态、清理 NF 多余订阅
    Phase 1.5 拉黑的订阅从 NF 取消
    Phase 2   本地 → NF：推送未完成的本地订阅
    Phase 3   电影完成态判断
    Phase 4   剧集完成态判断（基于本地 Emby/TMDB 缓存）
    Phase 5   记录 NF 已取消条目
    Phase 6   记录同步活动日志
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import init_logger
from app.models.subscription import Subscription
from app.schemas.subscription import SubscriptionSyncResult
from app.services.activity import log_activity
from app.services.nextfind import NextFindService
from app.services.nf_sync.phases import (
    phase0_clean_abnormal,
    phase1_5_blacklist,
    phase1_nf_to_local,
    phase2_local_to_nf,
    phase3_movie_completed,
    phase4_tv_completed,
    phase5_log_cancelled,
)

logger = init_logger()


class NfSyncEngine:
    """NextFind 双向同步引擎 — 以本地数据库为准同步 NF 订阅状态。"""

    def __init__(self, nf_service: NextFindService):
        """初始化同步引擎。

        Args:
            nf_service: NextFind 服务实例
        """
        self.nf = nf_service

    async def sync(self, db: AsyncSession) -> list[SubscriptionSyncResult]:
        """执行双向同步 — 以本地数据库为准，确保 NF 与本地一致。

        NF 可能对同一 tmdb_id 返回多条记录（tv + movie），需要全部遍历处理。

        Args:
            db: 数据库会话

        Returns:
            每条操作的同步结果列表
        """
        nf_subs = await self.nf.get_subscriptions()

        # 按 tmdb_id 分组，保留所有条目（NF 可能同一 tmdb_id 有 tv + movie 两条）
        nf_by_tmdb: dict[int, list[dict]] = {}
        for s in nf_subs:
            tid = s.get("tmdb_id")
            if tid:
                nf_by_tmdb.setdefault(int(tid), []).append(s)

        results: list[SubscriptionSyncResult] = []

        # 获取本地所有订阅
        local_all = (await db.execute(select(Subscription))).scalars().all()
        local_by_tmdb: dict[int, Subscription] = {s.tmdb_id: s for s in local_all}

        await phase0_clean_abnormal(self.nf, nf_subs, results)
        await phase1_nf_to_local(self.nf, nf_by_tmdb, local_by_tmdb, results)
        await phase1_5_blacklist(self.nf, local_all, nf_by_tmdb, results)
        await phase2_local_to_nf(self.nf, local_all, nf_by_tmdb, results)
        phase3_movie_completed(nf_by_tmdb, local_by_tmdb)
        await phase4_tv_completed(db, local_all)
        phase5_log_cancelled(nf_by_tmdb, local_by_tmdb)

        # === Phase 6: 记录同步活动 ===
        await log_activity(db, "sync", f"双向同步完成: 处理了 {len(results)} 条记录")
        await db.commit()

        return results
