"""活动日志数据模型。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ActivityLog(Base):
    """活动日志表 — 记录所有操作历史（订阅、取消、搜索、同步等）。"""

    __tablename__ = "activity_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="操作类型: subscribe / unsubscribe / mp_search / mp_downloaded / system / sync",
    )
    tmdb_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="关联的 TMDB ID"
    )
    message: Mapped[str] = mapped_column(Text, nullable=False, comment="日志消息")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
