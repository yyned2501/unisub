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
            if season is None:
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
            - 已补齐（缺集清零）的季：删 MP 订阅 + 删子表行

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
            if sn is not None:
                missing_seasons[int(sn)] = item

        # 新出现的缺集季 → 建订阅
        for sn, item in missing_seasons.items():
            if sn not in rows_by_season:
                await self._create_mp_sub(db, sub, season=sn, missing_info=item)

        # 已补齐的季（子表有但 MP 已不缺）→ 删订阅 + 删子表行
        for sn, row in rows_by_season.items():
            if sn is None or sn in missing_seasons:
                continue
            if row.mp_sub_id is not None:
                result = await self.mp.delete_subscription(row.mp_sub_id)
                if "error" in result:
                    logger.warning("MP 删除已补齐季失败: %s 第%d季, %s", sub.title, sn, result)
                    continue
            await db.delete(row)
            logger.info("MP 镜像 — 季已补齐，删除订阅: %s 第%d季", sub.title, sn)

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
        """查询剧集缺集季。失败返回 None，无缺集返回 []。

        季集结构（seasons）优先取本地 tmdb_season 缓存；本地缺失时通过 TMDB
        服务查询并落库（get_seasons_map 内部处理）。拿到 seasons 后交给 MP
        notexists 逐季比对，避免直接访问 MP media 接口。
        """
        seasons_map: dict[int, list[int]] | None = None
        if self.tmdb:
            try:
                seasons_map = await self.tmdb.get_seasons_map(db, sub.tmdb_id)
            except Exception as e:
                logger.warning("获取季集结构失败: %s (tmdb_id=%d), %s", sub.title, sub.tmdb_id, e)

        if not seasons_map:
            # 拿不到季集结构 → MP notexists 无法逐季比对，跳过本条镜像
            logger.debug("无季集结构，跳过 MP 缺集查询: %s (tmdb_id=%d)", sub.title, sub.tmdb_id)
            return None

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
