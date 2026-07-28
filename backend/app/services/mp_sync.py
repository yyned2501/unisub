"""MoviePilot 订阅镜像引擎。

把 UniSub 订阅镜像到 MoviePilot：
    - subscribe: 按缺集季在 MP 建订阅（电影建单条无季订阅），写入 mp_subscription 子表
    - unsubscribe: 删除该订阅在 MP 的所有订阅条目与子表行
    - sync: 对存量订阅重算缺集季，新增季建订阅、已补齐季删订阅、存量季回写进度

MP 的缺集判断来自 ``POST /api/v1/mediaserver/notexists``（依赖 MP 已配置媒体服务器）。
所有 MP 操作均为 best-effort：失败只记日志，不阻塞 NF 主通道。
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import init_logger
from app.models.activity_log import ActivityLog
from app.models.emby_cache import EmbyCache
from app.models.emby_season_cache import EmbySeasonCache
from app.models.mp_subscription import MpSubscription
from app.models.subscription import Subscription
from app.services.moviepilot import MoviePilotService
from app.services.tmdb import TMDBService

logger = init_logger()


class MpSyncEngine:
    """MoviePilot 订阅镜像引擎 — 维护 mp_subscription 子表与 MP 端一致。"""

    def __init__(self, mp_service: MoviePilotService, tmdb_service: TMDBService | None = None):
        """初始化引擎。

        Args:
            mp_service: MoviePilot 服务实例
            tmdb_service: TMDB 服务实例（可选）。用于本地缺季集数据时调 TMDB
                补缓存；未提供时剧集缺集查询无法补数据，会跳过镜像。
        """
        self.mp = mp_service
        self.tmdb = tmdb_service

    async def subscribe(self, db: AsyncSession, sub: Subscription) -> None:
        """为订阅创建 MP 镜像。

        电影：直接建一条无季订阅。电视剧：先查缺集季，逐季建订阅；
        查不到缺集信息（如 MP 未配媒体服务器）时跳过，不阻塞。

        Args:
            db: 数据库会话（调用方负责 commit）
            sub: 本地订阅记录
        """
        if sub.media_type == "movie":
            await self._create_mp_sub(db, sub, season=None)
            return

        seasons = await self._query_missing_seasons(db, sub)
        if seasons is None:
            # 查询失败，跳过镜像（不阻塞）
            return
        if not seasons:
            logger.info("MP 镜像 — 剧集无缺集季，跳过: %s (tmdb_id=%d)", sub.title, sub.tmdb_id)
            return
        for item in seasons:
            season = item.get("season")
            # 跳过特典季（season=0）与缺季号的条目
            if season is None or int(season) == 0:
                continue
            await self._create_mp_sub(db, sub, season=int(season), missing_info=item)

    async def unsubscribe(self, db: AsyncSession, sub: Subscription) -> None:
        """删除订阅在 MP 的所有镜像条目。

        Args:
            db: 数据库会话（调用方负责 commit）
            sub: 本地订阅记录
        """
        rows = (
            (await db.execute(select(MpSubscription).where(MpSubscription.subscription_id == sub.id))).scalars().all()
        )
        for row in rows:
            if row.mp_sub_id is not None:
                result = await self.mp.delete_subscription(row.mp_sub_id)
                if "error" in result:
                    logger.warning("MP 取消订阅失败: %s 第%s季, %s", sub.title, row.season, result)
            await db.delete(row)
        if rows:
            logger.info("MP 镜像清理: %s (tmdb_id=%d, %d 条)", sub.title, sub.tmdb_id, len(rows))

    async def sync(self, db: AsyncSession) -> None:
        """同步所有活跃订阅的 MP 镜像 — 重算缺集季并回写进度。

        遍历未完成的本地订阅：
            - 存量子表行：拉 MP 详情回写缺集/完成数
            - 电视剧新出现的缺集季：建 MP 订阅
            - 已完结且补齐的季：删 MP 订阅 + 删子表行（未完结的季即便暂不缺集也保留）

        Args:
            db: 数据库会话
        """
        subs = (
            (
                await db.execute(
                    select(Subscription).where(
                        Subscription.completed == False,
                        Subscription.blacklisted == False,
                    )
                )
            )
            .scalars()
            .all()
        )
        for sub in subs:
            try:
                await self._sync_one(db, sub)
            except Exception as e:  # 单条失败不影响整体同步
                logger.error("MP 同步单条失败: %s (tmdb_id=%d), %s", sub.title, sub.tmdb_id, e)
        await db.commit()

    async def _sync_one(self, db: AsyncSession, sub: Subscription) -> None:
        """同步单个订阅的 MP 镜像。"""
        rows = (
            (await db.execute(select(MpSubscription).where(MpSubscription.subscription_id == sub.id))).scalars().all()
        )
        rows_by_season: dict[int | None, MpSubscription] = {r.season: r for r in rows}

        # 存量行：回写 MP 进度
        for row in rows:
            await self._refresh_row(sub, row)

        if sub.media_type == "movie":
            # 电影：无季，只需保证有一条镜像（缺则补建）
            if None not in rows_by_season:
                await self._create_mp_sub(db, sub, season=None)
            return

        # 电视剧：重算缺集季
        seasons = await self._query_missing_seasons(db, sub)
        if seasons is None:
            return  # 查询失败，本轮跳过
        missing_seasons: dict[int, dict] = {}
        for item in seasons:
            sn = item.get("season")
            # 跳过特典季（season=0），不对其建订阅
            if sn is not None and int(sn) != 0:
                missing_seasons[int(sn)] = item

        # 新出现的缺集季 → 建订阅
        for sn, item in missing_seasons.items():
            if sn not in rows_by_season:
                await self._create_mp_sub(db, sub, season=sn, missing_info=item)

        # 已补齐的季（子表有但 MP 已不缺）：仅当该季已完结才删订阅。
        # 未完结的季（已播 < 总集数，后续还有集要播）即便暂不缺集也保留订阅，
        # 避免"追平即删、下集播出又重建"的反复。
        filled = [sn for sn in rows_by_season if sn is not None and sn not in missing_seasons]
        completion: dict[int, bool] = {}
        if filled and self.tmdb:
            completion = await self.tmdb.get_season_completion(db, sub.tmdb_id)
        for sn in filled:
            if not completion.get(sn, False):
                logger.debug("MP 镜像 — 季暂不缺集但未完结，保留订阅: %s 第%d季", sub.title, sn)
                continue
            row = rows_by_season[sn]
            if row.mp_sub_id is not None:
                result = await self.mp.delete_subscription(row.mp_sub_id)
                if "error" in result:
                    logger.warning("MP 删除已完结季失败: %s 第%d季, %s", sub.title, sn, result)
                    continue
            await db.delete(row)
            logger.info("MP 镜像 — 季已完结且补齐，删除订阅: %s 第%d季", sub.title, sn)

    async def _create_mp_sub(
        self,
        db: AsyncSession,
        sub: Subscription,
        season: int | None,
        missing_info: dict | None = None,
    ) -> None:
        """在 MP 创建一条订阅并写入子表。失败仅记日志。"""
        # 防重：MP 端已存在则直接关联
        existing = await self.mp.find_subscription(sub.tmdb_id, season=season)
        mp_sub_id = _extract_sub_id(existing)

        if mp_sub_id is None:
            result = await self.mp.create_subscription(
                sub.tmdb_id, sub.media_type, sub.title, year=sub.year, season=season
            )
            if "error" in result:
                logger.warning("MP 创建订阅失败: %s 第%s季, %s", sub.title, season, result)
                return
            if result.get("success") is False:
                logger.warning("MP 创建订阅未成功: %s 第%s季, %s", sub.title, season, result)
                return
            mp_sub_id = _extract_sub_id(result)

        row = MpSubscription(
            id=str(uuid.uuid4()),
            subscription_id=sub.id,
            tmdb_id=sub.tmdb_id,
            season=season,
            mp_sub_id=mp_sub_id,
            mp_status=None,
            mp_missing_eps=len(missing_info.get("episodes", [])) if missing_info else 0,
            mp_completed_eps=0,
            mp_total_eps=int((missing_info or {}).get("total_episode") or 0),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(row)
        label = "电影" if season is None else f"第{season}季"
        logger.info("MP 镜像 — 创建订阅: %s %s (mp_sub_id=%s)", sub.title, label, mp_sub_id)

        log_entry = ActivityLog(
            id=str(uuid.uuid4()),
            action="subscribe",
            tmdb_id=sub.tmdb_id,
            message=f"MP 镜像订阅: {sub.title} {label}",
            created_at=datetime.now(UTC),
        )
        db.add(log_entry)

    async def _refresh_row(self, sub: Subscription, row: MpSubscription) -> None:
        """拉取 MP 订阅详情回写进度到子表行。"""
        if row.mp_sub_id is None:
            return
        detail = await self.mp.get_subscription_detail(row.mp_sub_id)
        if "error" in detail:
            return
        row.mp_status = detail.get("state")
        total = int(detail.get("total_episode") or 0)
        lack = int(detail.get("lack_episode") or 0)
        completed = detail.get("completed_episode")
        row.mp_total_eps = total
        row.mp_missing_eps = lack
        if completed is not None:
            row.mp_completed_eps = int(completed)
        elif total:
            row.mp_completed_eps = max(0, total - lack)
        row.updated_at = datetime.now(UTC)

    async def _query_missing_seasons(self, db: AsyncSession, sub: Subscription) -> list[dict] | None:
        """查询剧集缺集季 — 优先本地计算，同步缺口才用 MP notexists 兜底。

        缺集 = 已播集数（tmdb_season）- 库内集数（emby_season_cache），纯本地 DB 计算，
        不再每轮实时调 MP notexists（其频繁打 Emby、慢且易 502）。判定路径：
            - 本地有按季库数据 → 本地算缺集
            - 本地无按季数据且剧不在 Emby 库 → 所有已播集都缺（本地判定，不调 notexists）
            - 本地无按季数据但剧在库（同步缺口）→ 回退调一次 notexists 兜底

        Returns:
            缺集季列表（``[{"season","episodes","total_episode"}, ...]``）；
            失败/无季集结构返回 None，无缺集返回 []。
        """
        seasons_map: dict[int, list[int]] | None = None
        if self.tmdb:
            try:
                seasons_map = await self.tmdb.get_seasons_map(db, sub.tmdb_id)
            except Exception as e:
                logger.warning("获取季集结构失败: %s (tmdb_id=%d), %s", sub.title, sub.tmdb_id, e)

        if not seasons_map:
            logger.debug("无季集结构，跳过 MP 缺集查询: %s (tmdb_id=%d)", sub.title, sub.tmdb_id)
            return None

        emby_counts = await self._emby_season_counts(db, sub.tmdb_id)
        if emby_counts:
            return self._diff_missing(seasons_map, emby_counts)

        if not await self._show_in_emby(db, sub.tmdb_id):
            # 剧不在 Emby 库 → 已播集全缺，本地直接判定，不调 notexists
            return self._diff_missing(seasons_map, {})

        # 剧在库但无按季缓存（同步缺口）→ notexists 兜底一次
        logger.debug("本地无按季库缓存，notexists 兜底: %s (tmdb_id=%d)", sub.title, sub.tmdb_id)
        return await self._query_missing_via_mp(sub, seasons_map)

    @staticmethod
    def _diff_missing(seasons_map: dict[int, list[int]], emby_counts: dict[int, int]) -> list[dict]:
        """本地计算缺集季，返回与 MP notexists 兼容的结构。

        假设库内集按序补齐（1..have），缺集为 have+1..aired。

        Args:
            seasons_map: ``{季号: [已播集号列表]}``（来自 tmdb_season）
            emby_counts: ``{季号: 库内集数}``（来自 emby_season_cache）

        Returns:
            缺集季列表（仅含 已播 > 库内 的季）
        """
        missing: list[dict] = []
        for sn, eps in seasons_map.items():
            aired = len(eps)
            have = emby_counts.get(sn, 0)
            if aired > have:
                missing.append({"season": sn, "episodes": list(range(have + 1, aired + 1)), "total_episode": aired})
        return missing

    async def _emby_season_counts(self, db: AsyncSession, tmdb_id: int) -> dict[int, int]:
        """读取本地 emby_season_cache 的按季库内集数 ``{季号: 集数}``。"""
        rows = (await db.execute(select(EmbySeasonCache).where(EmbySeasonCache.tmdb_id == tmdb_id))).scalars().all()
        return {row.season: (row.episode_count or 0) for row in rows}

    async def _show_in_emby(self, db: AsyncSession, tmdb_id: int) -> bool:
        """判断剧是否在 Emby 库中（emby_cache 有该 tmdb_id 记录）。"""
        row = (await db.execute(select(EmbyCache.tmdb_id).where(EmbyCache.tmdb_id == tmdb_id))).first()
        return row is not None

    async def _query_missing_via_mp(self, sub: Subscription, seasons_map: dict[int, list[int]]) -> list[dict] | None:
        """兜底：调 MP notexists 查缺集（仅本地按季缓存缺口时使用）。"""
        result = await self.mp.get_missing_seasons(
            sub.tmdb_id, sub.media_type, sub.title, year=sub.year, seasons=seasons_map
        )
        if isinstance(result, dict) and "error" in result:
            logger.warning("MP 缺集查询失败（跳过镜像）: %s, %s", sub.title, result)
            return None
        if not isinstance(result, list):
            return None
        return result


def _extract_sub_id(payload: dict | list | None) -> int | None:
    """从 MP 响应中提取订阅 ID。

    兼容多种返回形态：``{"data": {"id": N}}``、``{"id": N}``、单元素列表。

    Args:
        payload: MP 响应内容

    Returns:
        订阅 ID 或 None
    """
    if not payload:
        return None
    if isinstance(payload, list):
        if not payload:
            return None
        payload = payload[0]
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, dict) and data.get("id") is not None:
        return int(data["id"])
    if payload.get("id") is not None:
        return int(payload["id"])
    return None
