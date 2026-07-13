"""平台配置数据模型。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PlatformConfig(Base):
    """平台配置表 — 存储 NextFind / MoviePilot 的连接信息。

    每条记录对应一个外部平台的 API 连接配置。
    """

    __tablename__ = "platform_configs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="平台名（nextfind / moviepilot）"
    )
    base_url: Mapped[str] = mapped_column(Text, nullable=False, comment="API 基础地址")
    api_key: Mapped[str] = mapped_column(Text, nullable=False, comment="鉴权密钥")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
