"""编排服务 — 协调 NextFind 和 MoviePilot 的订阅与同步逻辑。

订阅 = 本地记录 + NextFind 添加
取消 = NextFind 移除 + 本地清理
同步 = 双向同步（NF ↔ US）确保两端一致
补充 = 对缺集条目调用 MoviePilot 搜索
"""

import uuid
from datetime import UTC, datetime

import asyncio

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import init_logger
from app.models.activity_log import ActivityLog
from app.models.emby_cache import EmbyCache
from app.models.subscription import Subscription
from app.models.tmdb_cache import TmdbCache
from app.schemas.subscription import SubscriptionResponse, SubscriptionSyncResult
from app.services.moviepilot import MoviePilotService
from app.services.nextfind import NextFindService
from app.services.tmdb import TMDBService

logger = init_logger()


def _parse_year(year_val: str | int | None) -> int | None:
    """安全解析年份值。

    Args:
        year_val: 原始年份值（字符串、数字或 None）

    Returns:
        整数年份或 None
    """
    if year_val is None:
        return None
    try:
        return int(year_val)
    except (ValueError, TypeError):
        return None


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
            mp_service: MoviePilot 服务实例（可选，仅补充搜索时需要）
            tmdb_service: TMDB 服务实例（可选，用于推断媒体类型）
        """
        self.nf = nf_service
        self.mp = mp_service
        self.tmdb = tmdb_service

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
        """创建订阅 — 先写本地库，再通知 NextFind 添加。

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
            source=source or "manual",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(sub)

        # 通知 NextFind 添加订阅
        nf_result = await self.nf.add_subscription(tmdb_id, title=title)
        if "error" not in nf_result:
            sub.nf_subscribed = True
            nf_id = nf_result.get("id") or nf_result.get("sub_id") or ""
            sub.nf_sub_id = str(nf_id) if nf_id else None
            logger.info(f"NextFind 订阅成功: {title} (tmdb_id={tmdb_id})")
        else:
            logger.error(f"NextFind 订阅失败: {title} (tmdb_id={tmdb_id}), {nf_result}")
            await db.rollback()
            raise HTTPException(
                status_code=502,
                detail=f"NextFind 订阅失败: {nf_result.get('detail', nf_result.get('error', '未知错误'))}",
            )

        # 记录活动日志
        log_entry = ActivityLog(
            id=str(uuid.uuid4()),
            action="subscribe",
            tmdb_id=tmdb_id,
            message=f"订阅了 {title} ({media_type})",
            created_at=datetime.now(UTC),
        )
        db.add(log_entry)

        await db.commit()
        await db.refresh(sub)

        return SubscriptionResponse.model_validate(sub)

    async def unsubscribe(self, db: AsyncSession, subscription_id: str) -> dict:
        """取消订阅 — 从 NextFind 移除，删除本地记录。

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
        nf_result = await self.nf.remove_subscription(sub.tmdb_id)
        if "error" in nf_result:
            logger.warning(f"NextFind 取消订阅失败: {sub.title}, {nf_result}")
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

        # 删除本地记录
        await db.delete(sub)
        await db.commit()

        return {"success": True, "message": f"已取消订阅 {sub.title}"}

    async def infer_media_type(
        self,
        nf_sub: dict,
        tmdb_service: TMDBService | None = None,
    ) -> str:
        """从 NF 订阅数据推断媒体类型，优先通过 TMDB API 确认。

        Args:
            nf_sub: NF 订阅数据字典
            tmdb_service: TMDB 服务实例（可选），有则调 API 确认

        Returns:
            "movie" 或 "tv"
        """
        raw = nf_sub.get("raw_type") or nf_sub.get("media_type") or nf_sub.get("type") or ""
        raw_lower = raw.lower()
        if raw_lower in ("movie", "电影"):
            return "movie"
        if raw_lower in ("tv", "剧集", "series"):
            return "tv"

        # 有 TMDB 服务时，调 API 确认类型
        tid = nf_sub.get("tmdb_id")
        if tid is not None and tmdb_service and tmdb_service.api_key:
            detail = await tmdb_service._get(f"/tv/{tid}")
            if detail and "error" not in detail and detail.get("name"):
                return "tv"
            detail = await tmdb_service._get(f"/movie/{tid}")
            if detail and "error" not in detail and detail.get("title"):
                return "movie"

        return "tv"

    async def sync_subscriptions(self, db: AsyncSession) -> list[SubscriptionSyncResult]:
        """同步订阅 —— 以本地数据库为准，确保 NF 与本地一致。

        1. NF → 本地: 更新本地已有记录的 nf_status/nf_missing_eps/completed；
           NF 有但本地没有的 → 从 NF 取消订阅（不导入本地）
        2. 本地 → NF: 本地有但 NF 未订阅的 → 推送到 NF
        3. 更新完成状态

        Args:
            db: 数据库会话

        Returns:
            每条操作的同步结果列表
        """
        nf_subs = await self.nf.get_subscriptions()
        nf_by_tmdb: dict[int, dict] = {}
        for s in nf_subs:
            tid = s.get("tmdb_id")
            if tid:
                nf_by_tmdb[int(tid)] = s

        results: list[SubscriptionSyncResult] = []

        # 获取本地所有订阅
        local_all = (await db.execute(select(Subscription))).scalars().all()
        local_by_tmdb: dict[int, Subscription] = {s.tmdb_id: s for s in local_all}

        # === Phase 0: 清理 NF 中元数据异常的订阅（无标题/无年份等）===
        for tid, nf_sub in nf_by_tmdb.items():
            title = (nf_sub.get("title") or nf_sub.get("name") or "").strip()
            if title:
                continue  # 有标题，跳过
            nf_status = nf_sub.get("sub_status") or nf_sub.get("status") or ""
            if str(nf_status).lower() in ("cancelled", "canceled", "stopped"):
                continue  # 已取消的不用再处理

            nf_result = await self.nf.remove_subscription(tid, media_type=nf_sub.get("media_type", "tv"))
            if "error" not in nf_result:
                results.append(
                    SubscriptionSyncResult(
                        tmdb_id=tid,
                        title=f"tmdb_{tid}",
                        action="cancelled_abnormal",
                        nf_subscribed=False,
                        message=f"NF 异常订阅已取消（无元数据）: tmdb_id={tid}",
                    )
                )
                logger.info(f"同步清理 — 取消 NF 异常订阅: tmdb_id={tid}")
            else:
                logger.warning(f"同步清理 — 取消 NF 异常订阅失败: tmdb_id={tid}, {nf_result}")

        # === Phase 1: NF → 本地（更新状态 + 清理 NF 多余订阅）===
        for tid, nf_sub in nf_by_tmdb.items():
            nf_status = nf_sub.get("sub_status") or nf_sub.get("status") or nf_sub.get("nf_status")

            # NF 已取消的订阅：本地有记录且未完成则重新订阅，本地无记录或已完成则跳过
            if nf_status and str(nf_status).lower() in ("cancelled", "canceled", "stopped"):
                local_sub = local_by_tmdb.get(tid)
                if not local_sub or local_sub.completed:
                    continue  # 孤儿或已完成 → 跳过（NF 不允许删除已取消条目）
                # 本地有记录且未完成 → 重新订阅到 NF
                nf_result = await self.nf.add_subscription(tid, title=local_sub.title)
                if "error" in nf_result:
                    logger.warning(f"双向同步 — 重新订阅到 NF 失败: {local_sub.title}, {nf_result}")
                    continue
                logger.info(f"双向同步 — 重新订阅到 NF: {local_sub.title} (tmdb_id={tid})")
                # 重新订阅成功 → 更新 sub_id，修正状态，fall through 到正常同步逻辑
                nf_id = nf_result.get("id") or nf_result.get("sub_id") or ""
                local_sub.nf_sub_id = str(nf_id) if nf_id else None
                nf_sub["sub_status"] = "active"
                nf_status = "active"

            total_eps = nf_sub.get("total_episodes", 0)
            local_eps = nf_sub.get("local_episodes", 0)
            if total_eps and local_eps is not None:
                nf_missing = max(0, int(total_eps) - int(local_eps))
            else:
                nf_missing = nf_sub.get("missing_eps") or nf_sub.get("fillable_episodes_count", 0)
            nf_missing = int(nf_missing) if nf_missing else 0

            local_sub = local_by_tmdb.get(tid)

            if local_sub:
                # 更新状态
                local_sub.nf_subscribed = True
                local_sub.nf_status = str(nf_status) if nf_status else None
                local_sub.nf_missing_eps = nf_missing
                # 电影：以 NF is_in_library 为准双向同步完成状态
                # ⚠️ 不能用 nf_missing==0 判断：NF 对电影恒返回 total_episodes=0，
                # 导致 nf_missing 永远为 0，会把所有电影误标完成。
                if local_sub.media_type == "movie":
                    in_library = bool(nf_sub.get("is_in_library")) or int(nf_sub.get("local_episodes") or 0) > 0
                    if in_library and not local_sub.completed:
                        local_sub.completed = True
                        logger.info(f"电影已入库，标记完成: {local_sub.title} (tmdb_id={tid})")
                    elif not in_library and local_sub.completed:
                        local_sub.completed = False
                        logger.info(f"电影不在本地库，取消完成标记: {local_sub.title} (tmdb_id={tid})")
                if not local_sub.year:
                    local_sub.year = _parse_year(nf_sub.get("year"))
                if not local_sub.poster_url:
                    poster = nf_sub.get("poster") or nf_sub.get("poster_url") or nf_sub.get("poster_path")
                    if poster:
                        if poster.startswith("/"):
                            poster = f"{self.nf.base_url}{poster}"
                        local_sub.poster_url = poster
                local_sub.updated_at = datetime.now(UTC)

                results.append(
                    SubscriptionSyncResult(
                        tmdb_id=tid,
                        title=local_sub.title,
                        action="updated",
                        nf_status=local_sub.nf_status,
                        nf_missing_eps=nf_missing,
                        nf_subscribed=True,
                        needs_mp_search=nf_missing > 0,
                        message=f"已同步: {local_sub.title}, 缺集 {nf_missing}",
                    )
                )
            else:
                # 本地没有 → 从 NF 取消
                title = nf_sub.get("title") or nf_sub.get("name") or f"tmdb_{tid}"
                nf_result = await self.nf.remove_subscription(tid, media_type=nf_sub.get("media_type", "tv"))
                if "error" not in nf_result:
                    results.append(
                        SubscriptionSyncResult(
                            tmdb_id=tid,
                            title=title,
                            action="cancelled_from_nf",
                            nf_subscribed=False,
                            message=f"NF 多余订阅已取消: {title}",
                        )
                    )
                    logger.info(f"双向同步 — 从 NF 取消多余订阅: {title} (tmdb_id={tid})")
                else:
                    logger.warning(f"双向同步 — 取消 NF 订阅失败: {title}, {nf_result}")

        # === Phase 2: 本地 → NF（推送未完成的本地订阅到 NF）===
        for local_sub in local_all:
            if local_sub.completed:
                continue
            # nf_subscribed=True 但 NF 全量列表中找不到 → 需要重新推送
            if local_sub.nf_subscribed and local_sub.tmdb_id in nf_by_tmdb:
                continue
            nf_result = await self.nf.add_subscription(local_sub.tmdb_id, title=local_sub.title)
            if "error" not in nf_result:
                local_sub.nf_subscribed = True
                nf_id = nf_result.get("id") or nf_result.get("sub_id") or ""
                local_sub.nf_sub_id = str(nf_id) if nf_id else None
                local_sub.updated_at = datetime.now(UTC)

                results.append(
                    SubscriptionSyncResult(
                        tmdb_id=local_sub.tmdb_id,
                        title=local_sub.title,
                        action="pushed_to_nf",
                        nf_subscribed=True,
                        message=f"已推送到 NF: {local_sub.title}",
                    )
                )
                logger.info(f"双向同步 — 推送订阅到 NF: {local_sub.title} (tmdb_id={local_sub.tmdb_id})")
            else:
                logger.warning(f"双向同步 — 推送订阅到 NF 失败: {local_sub.title}, {nf_result}")

        # === Phase 3: 更新完成状态（仅电影；TV 由 Phase 4 基于 TMDB 数据判断）===
        for tid, nf_sub in nf_by_tmdb.items():
            local_sub = local_by_tmdb.get(tid)
            if not local_sub or local_sub.media_type != "movie":
                continue
            nf_status = nf_sub.get("sub_status") or nf_sub.get("status") or nf_sub.get("nf_status")
            if nf_status and str(nf_status) in ("completed", "finished"):
                local_sub.completed = True
                local_sub.updated_at = datetime.now(UTC)

        # === Phase 4: 基于本地 Emby/TMDB 缓存判断剧集入库完成 ===
        # 完结剧（tmdb_aired_eps 为 None）：emby >= tmdb_total_eps → completed
        # 在播剧（tmdb_aired_eps 有值）：emby >= tmdb_aired_eps → aired_complete（不标 completed）
        # ⚠️ 电影不走这里：emby_cache 只存剧集，电影完成状态由 Phase 1 的 NF is_in_library 判断
        unfinished_tids = [s.tmdb_id for s in local_all if not s.completed and s.media_type == "tv"]
        if unfinished_tids:
            emby_rows = (
                (await db.execute(select(EmbyCache).where(EmbyCache.tmdb_id.in_(unfinished_tids)))).scalars().all()
            )
            emby_map = {e.tmdb_id: e for e in emby_rows}
            tmdb_rows = (
                (await db.execute(select(TmdbCache).where(TmdbCache.tmdb_id.in_(unfinished_tids)))).scalars().all()
            )
            tmdb_map = {t.tmdb_id: t for t in tmdb_rows}

            for sub in local_all:
                if sub.completed or sub.media_type != "tv":
                    continue
                ec = emby_map.get(sub.tmdb_id)
                if not ec or not ec.emby_episode_count:
                    continue

                tc = tmdb_map.get(sub.tmdb_id)
                if not tc:
                    continue
                if tc.tmdb_aired_eps:
                    # 在播剧：已播出集数全部入库 → aired_complete
                    if ec.emby_episode_count >= tc.tmdb_aired_eps and not sub.aired_complete:
                        sub.aired_complete = True
                        sub.updated_at = datetime.now(UTC)
                        logger.info(
                            f"在播剧已播出集数全部入库: {sub.title} "
                            f"(emby={ec.emby_episode_count}, aired={tc.tmdb_aired_eps})"
                        )
                elif tc.tmdb_total_eps:
                    # 完结剧：总集数全部入库 → completed
                    if ec.emby_episode_count >= tc.tmdb_total_eps:
                        sub.completed = True
                        sub.updated_at = datetime.now(UTC)
                        logger.info(
                            f"完结剧已全部入库: {sub.title} (emby={ec.emby_episode_count}, total={tc.tmdb_total_eps})"
                        )

        # === Phase 5: 清理 NF 中不再需要的 cancelled 条目 ===
        # 经过 Phase 1-4 后，清理两种无效订阅：
        #   1. 孤儿条目（本地无记录）→ 直接删
        #   2. 已完成条目（本地 completed）→ 删
        # 未完成且本地有记录的 cancelled 由 Phase 1 重新订阅，这里不动。
        cleaned = 0
        for tid, nf_sub in nf_by_tmdb.items():
            nf_status = nf_sub.get("sub_status") or nf_sub.get("status") or nf_sub.get("nf_status")
            if not nf_status or str(nf_status).lower() not in ("cancelled", "canceled", "stopped"):
                continue
            local_sub = local_by_tmdb.get(tid)
            if local_sub and not local_sub.completed:
                continue  # 未完成，Phase 1 会重新订阅
            reason = "本地已完成" if local_sub else "本地无记录"
            nf_result = await self.nf.remove_subscription(tid, media_type=nf_sub.get("media_type", "tv"))
            if "error" not in nf_result:
                cleaned += 1
                logger.info(f"同步清理 — 删除 NF 无效订阅: tmdb_id={tid} ({reason})")
            else:
                logger.warning(f"同步清理 — 删除 NF 无效订阅失败: tmdb_id={tid}, {nf_result}")
        if cleaned:
            logger.info(f"同步清理 — 本轮共删除 {cleaned} 条 NF 无效订阅")

        # === Phase 6: 记录同步活动 ===
        log_entry = ActivityLog(
            id=str(uuid.uuid4()),
            action="sync",
            tmdb_id=None,
            message=f"双向同步完成: 处理了 {len(results)} 条记录",
            created_at=datetime.now(UTC),
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
                message=(f"MP 补充搜索: {sub.title} ({sub.media_type}), 缺集 {sub.nf_missing_eps}"),
                created_at=datetime.now(UTC),
            )
            db.add(log_entry)

        await db.commit()
        logger.info(f"MP 补充搜索完成: 处理了 {len(results)} 条缺集订阅")
        return results
