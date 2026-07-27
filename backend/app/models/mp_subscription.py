"""MoviePilot 订阅数据模型。

一个 UniSub 订阅（subscriptions 表，整剧一行）可对应多条 MoviePilot 订阅
（MP 订阅粒度按季），故用独立子表存储。电影订阅 season 为 NULL。
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MpSubscription(Base):
    """MoviePilot 订阅子表 — 记录镜像到 MP 的按季订阅。

    通过 subscription_id 关联 subscriptions 表；(subscription_id, season)
    唯一，season 为 NULL（电影）时由应用层保证一个订阅只有一条。
    """

    __tablename__ = "mp_subscription"
    __table_args__ = (
        Index("ix_mp_subscription_sub_season", "subscription_id", "season", unique=True),
        Index("ix_mp_subscription_tmdb_id", "tmdb_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    subscription_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联 subscriptions.id",
    )
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="TMDB ID")
    season: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="季号（电影为 NULL）")
    mp_sub_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="MoviePilot 订阅 ID")
    mp_status: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="MP 状态: N-新建 / R-订阅中")
    mp_missing_eps: Mapped[int] = mapped_column(Integer, default=0, comment="MP 缺集数量")
    mp_completed_eps: Mapped[int] = mapped_column(Integer, default=0, comment="MP 已完成集数")
    mp_total_eps: Mapped[int] = mapped_column(Integer, default=0, comment="MP 总集数")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
