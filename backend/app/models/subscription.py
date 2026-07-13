"""订阅数据模型。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Subscription(Base):
    """订阅记录表 — 跟踪用户的媒体订阅状态。

    同时记录 NextFind 端的同步状态：是否已订阅、缺集数量等。
    """

    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="TMDB ID")
    media_type: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="媒体类型: movie / tv"
    )
    title: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="媒体标题"
    )
    poster_url: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="海报 URL"
    )
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="发行年份")
    nf_subscribed: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否已添加到 NextFind"
    )
    nf_status: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="NF 状态: active / missing_fill / completed"
    )
    nf_missing_eps: Mapped[int] = mapped_column(
        Integer, default=0, comment="NF 缺集数量"
    )
    nf_sub_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="NextFind 订阅 ID"
    )
    completed: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否已全部入库"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
