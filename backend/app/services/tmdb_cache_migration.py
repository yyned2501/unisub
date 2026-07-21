"""TMDB 缓存数据迁移 — 从旧 emby_cache 表复制 TMDB 数据到新 tmdb_cache 表。

在应用启动时自动执行，幂等（后续启动不会重复迁移）。
"""

from sqlalchemy import select, text

from app.core.database import async_session
from app.core.logger import init_logger
from app.models.tmdb_cache import TmdbCache

logger = init_logger()


async def migrate_tmdb_cache():
    """将旧 emby_cache 表中的 TMDB 字段迁移到 tmdb_cache 表。

    通过 SQL INSERT … SELECT … WHERE NOT EXISTS 实现幂等迁移。
    """
    async with async_session() as db:
        try:
            # 检查 emby_cache 表是否存在且有关联字段
            check = await db.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='emby_cache' AND column_name='tmdb_total_eps'"
                )
            )
            if not check.scalar():
                logger.info("TMDB 迁移跳过: emby_cache 表无 tmdb 字段（已迁移过）")
                return

            # 检查 tmdb_cache 是否已有数据
            existing = await db.execute(select(TmdbCache).limit(1))
            if existing.scalar_one_or_none():
                logger.info("TMDB 迁移跳过: tmdb_cache 表已有数据")
                return

            # 执行迁移
            result = await db.execute(
                text(
                    "INSERT INTO tmdb_cache (tmdb_id, tmdb_total_eps, tmdb_aired_eps, "
                    "tmdb_next_air_date, poster_url, tmdb_poster_path, updated_at) "
                    "SELECT e.tmdb_id, e.tmdb_total_eps, e.tmdb_aired_eps, "
                    "e.tmdb_next_air_date, e.poster_url, e.tmdb_poster_path, e.updated_at "
                    "FROM emby_cache e "
                    "WHERE (e.tmdb_total_eps IS NOT NULL OR e.tmdb_aired_eps IS NOT NULL) "
                    "AND NOT EXISTS (SELECT 1 FROM tmdb_cache t WHERE t.tmdb_id = e.tmdb_id)"
                )
            )
            await db.commit()
            logger.info(f"TMDB 数据迁移完成: 共 {result.rowcount} 条记录")
        except Exception as e:
            logger.error(f"TMDB 数据迁移失败: {e}")
