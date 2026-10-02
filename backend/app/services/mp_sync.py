"""MoviePilot 订阅镜像引擎。

把 UniSub 订阅镜像到 MoviePilot：
    - subscribe: 按缺集季在 MP 建订阅（电影建单条无季订阅），写入 mp_subscription 子表
    - unsubscribe: 删除该订阅在 MP 的所有订阅条目与子表行
    - sync: 对存量订阅重算缺集季，新增季建订阅、已补齐季删订阅、存量季回写进度

MP 的缺集判断优先本地计算（见 mp_missing.py），同步缺口才回退
``POST /api/v1/mediaserver/notexists`` 兜底。
所有 MP 操作均为 best-effort：失败只记日志，不阻塞 NF 主通道。
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import init_logger
from app.models.mp_subscription import MpSubscription
from app.models.subscription import Subscription
from app.services.activity import log_activity
from app.services.moviepilot import MoviePilotService
from app.services.mp_missing import query_missing_seasons, show_in_emby
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

    async def subscribe(self, db: AsyncSession, sub: Subscription) -> list[int]:
        """为订阅创建 MP 镜像，并返回本次**新建**的 MP 订阅 id。

        电影：直接建一条无季订阅。电视剧：先查缺集季，逐季建订阅；
        查不到缺集信息（如 MP 未配媒体服务器）时跳过，不阻塞。

        Args:
            db: 数据库会话（调用方负责 commit）
            sub: 本地订阅记录

        Returns:
            本次调用在 MP **新建**的订阅 id 列表（命中 MP 已存在订阅而直接关联的、
            以及失败的都不计入）。调用方据此在「本地订阅已被取消」时精确撤销
            刚建的那一条（docs/SPEC-CANCEL-RACE.md §8.3-B），不做全量上游对账。
        """
        if sub.media_type == "movie":
            mp_sub_id = await self._create_mp_sub(db, sub, season=None)
            return [mp_sub_id] if mp_sub_id is not None else []

        created: list[int] = []
        seasons = await query_missing_seasons(self, db, sub)
        if seasons is None:
            # 查询失败，跳过镜像（不阻塞）
            return created
        if not seasons:
            logger.info("MP 镜像 — 剧集无缺集季，跳过: %s (tmdb_id=%d)", sub.title, sub.tmdb_id)
            return created
        for item in seasons:
            season = item.get("season")
            # 跳过特典季（season=0）与缺季号的条目
            if season is None or int(season) == 0:
                continue
            mp_sub_id = await self._create_mp_sub(db, sub, season=int(season), missing_info=item)
            if mp_sub_id is not None:
                created.append(mp_sub_id)
        return created

    async def unsubscribe(self, db: AsyncSession, sub: Subscription) -> None:
        """删除订阅在 MP 的所有镜像条目。

        Args:
            db: 数据库会话（调用方负责 commit）
            sub: 本地订阅记录
        """
        rows = await self._load_rows(db, sub.id)
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
        rows = await self._load_rows(db, sub.id)
        rows_by_season: dict[int | None, MpSubscription] = {r.season: r for r in rows}

        # 电视剧：只镜像已在 Emby 库的剧（补 gap）。不在库 → 清掉已有镜像、不新建，
        # 先于进度回写处理，避免对将被清理的订阅做无效 MP 调用。
        if sub.media_type != "movie" and not await show_in_emby(db, sub.tmdb_id):
            for row in rows:
                if row.mp_sub_id is not None:
                    result = await self.mp.delete_subscription(row.mp_sub_id)
                    if "error" in result:
                        logger.warning("MP 清理不在库剧订阅失败: %s 第%s季, %s", sub.title, row.season, result)
                await db.delete(row)
            if rows:
                logger.info(
                    "MP 镜像 — 剧不在 Emby 库，清理镜像: %s (tmdb_id=%d, %d 条)", sub.title, sub.tmdb_id, len(rows)
                )
            return

        # 存量行：回写 MP 进度
        for row in rows:
            await self._refresh_row(sub, row)

        if sub.media_type == "movie":
            # 电影：无季，只需保证有一条镜像（缺则补建）
            if None not in rows_by_season:
                await self._create_mp_sub(db, sub, season=None)
            return

        # 电视剧：重算缺集季
        seasons = await query_missing_seasons(self, db, sub)
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

    async def _load_rows(self, db: AsyncSession, subscription_id: str) -> list[MpSubscription]:
        """加载指定订阅的全部 mp_subscription 子表行。

        Args:
            db: 数据库会话
            subscription_id: 本地订阅记录 UUID

        Returns:
            子表行列表（无记录时为空列表）
        """
        result = await db.execute(select(MpSubscription).where(MpSubscription.subscription_id == subscription_id))
        return list(result.scalars().all())

    async def _create_mp_sub(
        self,
        db: AsyncSession,
        sub: Subscription,
        season: int | None,
        missing_info: dict | None = None,
    ) -> int | None:
        """在 MP 创建一条订阅并写入子表。失败仅记日志。

        Returns:
            本次**新建**的 MP 订阅 id；命中 MP 已存在订阅（只关联、不新建）
            或创建失败时返回 None（调用方据此决定取消时撤哪一条）。
        """
        # 防重：MP 端已存在则直接关联
        existing = await self.mp.find_subscription(sub.tmdb_id, season=season)
        mp_sub_id = _extract_sub_id(existing)
        created_now = False

        if mp_sub_id is None:
            result = await self.mp.create_subscription(
                sub.tmdb_id, sub.media_type, sub.title, year=sub.year, season=season
            )
            if "error" in result or result.get("success") is False:
                if "error" in result:
                    logger.warning("MP 创建订阅失败: %s 第%s季, %s", sub.title, season, result)
                else:
                    logger.warning("MP 创建订阅未成功: %s 第%s季, %s", sub.title, season, result)
                # 「报告失败」不等于上游没建出来：MP 建订阅实测会超过客户端超时
                # （2026-10-02 真机：30s 超时返回 request_failed，MP 其实已建 → 留下
                # unisub 无记录的僵尸订阅 mp_sub_id=2268）。复扫一次，扫到就按「本次新建」
                # 处理：写子表被本地记录，取消补偿时也撤得掉。
                try:
                    existing = await self.mp.find_subscription(sub.tmdb_id, season=season)
                except Exception as exc:  # 复扫失败按「没建出来」处理，保持 best-effort
                    logger.debug("MP 创建报错后复扫失败: %s 第%s季, %s", sub.title, season, exc)
                    return None
                mp_sub_id = _extract_sub_id(existing)
                if mp_sub_id is None:
                    return None
                logger.warning(
                    "MP 创建订阅报错但上游已建（按本次新建处理）: %s 第%s季, mp_sub_id=%s",
                    sub.title,
                    season,
                    mp_sub_id,
                )
            else:
                mp_sub_id = _extract_sub_id(result)
            created_now = True

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

        await log_activity(db, "subscribe", f"MP 镜像订阅: {sub.title} {label}", tmdb_id=sub.tmdb_id)

        return mp_sub_id if created_now else None

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
