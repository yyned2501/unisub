"""CloudDrive2 配置数据模型。"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Cd2Config(Base):
    """CloudDrive2 配置表。"""

    __tablename__ = "cd2_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    base_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    api_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_path: Mapped[str] = mapped_column(Text, nullable=False, default="/115open/待整理/转存/")
    path_prefix: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="Emby 路径前缀（如 /media/Symedia）"
    )
    path_replacement: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="替换为 CD2 路径（如 /115open/已整理）"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
