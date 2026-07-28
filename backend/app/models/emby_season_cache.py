"""Emby 按季库集数缓存模型。

将 Emby 媒体库中「每部剧每一季实际有多少个剧集文件」定期同步到本地，
供 MP 镜像订阅在本地计算缺集（已播集数 - 库内集数），避免每轮订阅同步都
实时调 MP notexists（其会频繁打 Emby、慢且易 502）。

数据在 EmbyService.sync_cache 批量拉取全库 Episode 时顺手按季统计写入
（同一次请求带 ParentIndexNumber 字段，零额外 Emby 调用）。与 tmdb_season
（TMDB 侧按季已播集数）对称：emby_season_cache 是 Emby 侧按季库内集数。
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EmbySeasonCache(Base):
    """Emby 按季库集数缓存表。

    (tmdb_id, season) 唯一；season=0 的特典季不入库（与 tmdb_season 一致）。
    """

    __tablename__ = "emby_season_cache"

    tmdb_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, comment="TMDB ID")
    season: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, comment="季号（不含特典季 0）")
    episode_count: Mapped[int] = mapped_column(Integer, default=0, comment="Emby 库中该季实际剧集文件数")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
