"""自动订阅 — 创建订阅（NextFind 远端 + 本地 DB）与订阅阶段收尾。"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import init_logger
from app.models.activity_log import ActivityLog
from app.models.subscription import Subscription
from app.services.auto_subscribe.models import (
    STATUS_ERROR,
    STATUS_EXISTS,
    STATUS_IN_LIBRARY,
    STATUS_SUBSCRIBED,
)
from app.services.nextfind import NextFindAuthError, NextFindService
from app.services.tmdb import TMDBService

logger = init_logger(__name__)


async def create_subscription(
    db: AsyncSession,
    nf_service: NextFindService,
    tmdb_id: int,
    title: str,
    media_type: str,
    poster: str | None,
    year: str | None,
) -> tuple[str, Subscription | None]:
    """确认 NextFind 订阅后再创建本地订阅记录。

    Returns:
        (outcome, sub): outcome 为 "created" / "already_exists" / "local_exists" / "failed"
    """
    existing = await db.execute(select(Subscription).where(Subscription.tmdb_id == tmdb_id))
    if existing.scalar_one_or_none():
        return "local_exists", None

    remote = await nf_service.create_subscription(tmdb_id, media_type, title=title)
    if remote.outcome == "failed":
        logger.error(
            "[自动订阅] NextFind 未确认订阅: tmdb_id=%s, reason=%s",
            tmdb_id,
            remote.message,
        )
        return "failed", None

    year_int = int(year) if year and str(year).isdigit() else None
    sub = Subscription(
        id=str(uuid.uuid4()),
        tmdb_id=tmdb_id,
        media_type=media_type,
        title=title,
        poster_url=poster,
        year=year_int,
        nf_subscribed=True,
        nf_sub_id=remote.subscription_id,
        nf_status=None,
        nf_missing_eps=0,
        source="auto_subscribe",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(sub)
    db.add(
        ActivityLog(
            id=str(uuid.uuid4()),
            action="subscribe",
            tmdb_id=tmdb_id,
            message=f"自动订阅: {title} ({media_type})",
            created_at=datetime.now(UTC),
        )
    )
    try:
        await db.flush()
        await db.refresh(sub)
    except Exception:
        logger.exception("[自动订阅] NextFind 已成功但本地持久化失败: tmdb_id=%s", tmdb_id)
        raise
    return remote.outcome, sub


async def finalize_subscription(
    db: AsyncSession,
    db_lock: asyncio.Lock,
    nf_service: NextFindService,
    tmdb_service: TMDBService | None,
    best: dict,
    tmdb_id: int,
    matched_title: str,
    media_type: str,
    poster: str | None,
    year: str | int | None,
    src_name: str,
) -> str:
    """订阅阶段收尾：写 TMDB 缓存 → 已订阅/已在库检查 → 远端创建 + 本地持久化。

    Returns:
        STATUS_* 常量：STATUS_SUBSCRIBED / STATUS_EXISTS / STATUS_IN_LIBRARY / STATUS_ERROR
    """
    # 写入 TMDB 缓存：既然查了 TMDB 就别浪费，写入数据库后续直接用
    if media_type == "tv" and tmdb_service:
        await tmdb_service.update_cache_for_tv(db, tmdb_id)

    # TMDB 搜索无 is_subscribed/is_in_library 字段，从本地 DB 查询
    if not best.get("is_subscribed"):
        existing = await db.execute(select(Subscription).where(Subscription.tmdb_id == tmdb_id))
        if existing.scalar_one_or_none():
            return STATUS_EXISTS

    if best.get("is_in_library"):
        return STATUS_IN_LIBRARY

    # 创建订阅：远端明确成功后才写入本地
    async with db_lock:
        try:
            outcome, sub = await create_subscription(db, nf_service, tmdb_id, matched_title, media_type, poster, year)
            if outcome == "created" and sub:
                logger.info(f"[自动订阅] 新增订阅: {matched_title} (tmdb_id={tmdb_id}, 来源={src_name})")
                return STATUS_SUBSCRIBED
            if outcome == "already_exists" and sub:
                logger.info(f"[自动订阅] NextFind 已有订阅，已同步本地记录: {matched_title}")
                return STATUS_EXISTS
            if outcome == "local_exists":
                return STATUS_EXISTS
            return STATUS_ERROR
        except NextFindAuthError:
            raise  # 鉴权失败向上传播以中止整轮
        except Exception as e:
            logger.error(f"[自动订阅] 订阅失败: {matched_title}: {e}")
            return STATUS_ERROR
