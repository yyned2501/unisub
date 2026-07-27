"""TMDB 季集数据缓存模型。

存储剧集按季的集数结构（第 N 季有多少集），供 MP 订阅计算缺集季时使用。
数据在 update_cache_for_tv 调 TMDB 详情时顺手写入，避免订阅同步重复访问
MP media 接口。与 tmdb_cache（整剧聚合）分离：季是一对多，独立表便于按季
精确读写。
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TmdbSeason(Base):
    """TMDB 季集缓存表 — 按季存储剧集结构。

    (tmdb_id, season) 唯一；season=0 的特典季不入库。
    """

    __tablename__ = "tmdb_season"

    tmdb_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, comment="TMDB ID")
    season: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, comment="季号（不含特典季 0）")
    episode_count: Mapped[int] = mapped_column(Integer, default=0, comment="该季总集数")
    air_date: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="该季首播日期")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
