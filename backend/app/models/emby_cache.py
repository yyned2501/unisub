"""Emby 媒体库缓存数据模型。

将 Emby 剧集数据定期同步到本地数据库，
避免每次前端请求都实时拉取 Emby API。

TMDB 补充数据存储在独立的 tmdb_cache 表，通过 tmdb_id 关联。
黑名单状态从 emby_blacklist 表动态查询，不在本表冗余存储。
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EmbyCache(Base):
    """Emby 媒体库缓存表 — 只存储 Emby 源数据。

    TMDB 补充数据在 tmdb_cache 表。缺集分析时通过 tmdb_id JOIN。
    is_blacklisted 由 emby_blacklist 表动态关联，不在本表存储。
    """

    __tablename__ = "emby_cache"

    tmdb_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, comment="TMDB ID")
    emby_series_id: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="Emby 中的 Series ID")
    emby_series_name: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="Emby 中的剧集名称")
    emby_year: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Emby 中的制作年份")
    emby_episode_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Emby 中的 RecursiveItemCount（实际文件数）"
    )
    emby_image_url: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Emby 海报 URL")
    overview: Mapped[str | None] = mapped_column(Text, nullable=True, comment="剧情简介")
    emby_path: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Emby 媒体路径（含 {tmdb-xxx} 文件夹名）"
    )
    emby_library_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="Emby 媒体库名称（如 电视剧、动漫）"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
