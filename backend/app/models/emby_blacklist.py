"""Emby 媒体库黑名单数据模型。"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EmbyBlacklist(Base):
    """Emby 媒体库黑名单表 — 用户手动隐藏的剧集。"""

    __tablename__ = "emby_blacklist"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, comment="TMDB ID")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
