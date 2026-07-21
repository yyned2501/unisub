"""TMDB 补充数据缓存模型。

将从 TMDB API 获取的剧集数据独立持久化，
不受 Emby 缓存同步影响，避免 Emby 不可用时丢失 TMDB 数据。
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TmdbCache(Base):
    """TMDB 补充数据缓存表 — 独立存储 TMDB 数据。

    与 EmbyCache 通过 tmdb_id 关联，Emby 同步不会影响本表数据。
    """

    __tablename__ = "tmdb_cache"

    tmdb_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, comment="TMDB ID")
    tmdb_total_eps: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="TMDB 总集数")
    tmdb_aired_eps: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="TMDB 已播出集数（仅连载中剧集）"
    )
    tmdb_next_air_date: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="TMDB 下一集播出日期")
    poster_url: Mapped[str | None] = mapped_column(Text, nullable=True, comment="TMDB 海报 URL")
    tmdb_poster_path: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="TMDB 原始海报路径")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
