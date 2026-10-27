"""维护任务 — MP 缺集补充搜索与 TMDB 缓存增量刷新。

两者都是「扫一遍本地/上游状态，按需触发一次外部动作」的定时任务，
与订阅生命周期（``orchestrator.py``）和上游推送（``orchestrator_upstream.py``）
无关，单独放一个模块。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import init_logger
from app.models.subscription import Subscription
from app.models.tmdb_cache import TmdbCache
from app.services.activity import log_activity
from app.services.moviepilot import MoviePilotService
from app.services.nextfind import NextFindService
from app.services.tmdb import TMDBService

logger = init_logger()


class MaintenanceMixin:
    """维护任务能力 — 由 ``OrchestratorService`` 组合，依赖其构造出的属性。"""

    nf: NextFindService
    mp: MoviePilotService | None
    tmdb: TMDBService | None

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
