"""Emby 数据库操作封装 — 缺集分析、黑名单管理。

将 routers/emby.py 中的数据库查询逻辑封装到此处，
遵循 routers → services → models 的调用链。
"""

from datetime import UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.emby_blacklist import EmbyBlacklist
from app.models.emby_cache import EmbyCache
from app.models.subscription import Subscription
from app.models.tmdb_cache import TmdbCache
from app.schemas.emby_cache import EmbyCacheResponse, EmbyMissingAnalysis


async def analyze_missing_library(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 50,
    library_name: str | None = None,
) -> EmbyMissingAnalysis:
    """从缓存表读取 Emby 剧集数据，支持分页和媒体库过滤。

    从 emby_cache 表读取，关联订阅表和黑名单表，
    只展示缺集数 > 0（emby_episode_count < tmdb_aired_eps）的条目。

    Args:
        db: 数据库会话
        page: 页码（从 1 开始）
        page_size: 每页条数
        library_name: 媒体库名称过滤（None 表示不过滤）

    Returns:
        缺集分析结果
    """
    # 1. 获取所有缓存剧集
    result = await db.execute(select(EmbyCache).order_by(EmbyCache.updated_at.desc()))
    cached_series = result.scalars().all()

    if not cached_series:
        return EmbyMissingAnalysis()

    # 2. 获取所有 TMDB 缓存数据
    tmdb_ids = [c.tmdb_id for c in cached_series]
    tmdb_result = await db.execute(select(TmdbCache).where(TmdbCache.tmdb_id.in_(tmdb_ids)))
    tmdb_map = {t.tmdb_id: t for t in tmdb_result.scalars().all()}

    # 3. 获取已订阅的 tmdb_id 集合
    sub_result = await db.execute(select(Subscription.tmdb_id).where(Subscription.media_type == "tv"))
    subscribed_ids = {row[0] for row in sub_result.all()}

    # 4. 获取黑名单 tmdb_id 集合
    bl_result = await db.execute(select(EmbyBlacklist.tmdb_id))
    blacklisted_ids = {row[0] for row in bl_result.all()}

    # 5. 收集所有媒体库名称
    all_libraries = sorted(set(c.emby_library_name for c in cached_series if c.emby_library_name))

    # 6. 遍历缓存，计算 adjusted_missing，只保留缺集剧集
    series_list: list[EmbyCacheResponse] = []
    subscribed_count = 0
    total = len(cached_series)

    for cache in cached_series:
        # 媒体库过滤
        if library_name and cache.emby_library_name != library_name:
            continue

        is_subscribed = cache.tmdb_id in subscribed_ids
        is_blacklisted = cache.tmdb_id in blacklisted_ids
        tc = tmdb_map.get(cache.tmdb_id)

        if is_subscribed:
            subscribed_count += 1

        # 从 TmdbCache 获取 TMDB 数据
        tmdb_total_eps = tc.tmdb_total_eps if tc else None
        tmdb_aired_eps = tc.tmdb_aired_eps if tc else None
        tmdb_next_air_date = tc.tmdb_next_air_date if tc else None
        poster_url = tc.poster_url if tc else None

        # 计算 adjusted_missing = aired - emby_episode_count
        adjusted = None
        if tmdb_aired_eps is not None and cache.emby_episode_count is not None:
            adjusted = max(0, tmdb_aired_eps - cache.emby_episode_count)
        elif tmdb_total_eps is not None and cache.emby_episode_count is not None:
            adjusted = max(0, tmdb_total_eps - cache.emby_episode_count)
        else:
            continue

        if adjusted <= 0:
            continue

        series_list.append(
            EmbyCacheResponse(
                tmdb_id=cache.tmdb_id,
                emby_series_name=cache.emby_series_name,
                emby_year=cache.emby_year,
                emby_episode_count=cache.emby_episode_count,
                emby_image_url=cache.emby_image_url,
                emby_library_name=cache.emby_library_name,
                overview=cache.overview,
                poster_url=poster_url,
                tmdb_total_eps=tmdb_total_eps,
                tmdb_aired_eps=tmdb_aired_eps,
                tmdb_next_air_date=tmdb_next_air_date,
                is_subscribed=is_subscribed,
                is_blacklisted=is_blacklisted,
                adjusted_missing=adjusted,
            )
        )

    # 7. 分页
    total_missing = len(series_list)
    total_pages = max(1, (total_missing + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    paged_series = series_list[start : start + page_size]

    return EmbyMissingAnalysis(
        total_series=total,
        subscribed_count=subscribed_count,
        missing_count=total_missing,
        series=paged_series,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        libraries=all_libraries,
    )


async def list_blacklist(db: AsyncSession) -> list[EmbyBlacklist]:
    """获取所有黑名单条目。

    Args:
        db: 数据库会话

    Returns:
        黑名单条目列表
    """
    result = await db.execute(select(EmbyBlacklist).order_by(EmbyBlacklist.created_at.desc()))
    return list(result.scalars().all())


async def add_blacklist_entry(db: AsyncSession, tmdb_id: int) -> dict:
    """添加 TMDB ID 到黑名单。

    Args:
        db: 数据库会话
        tmdb_id: TMDB ID

    Returns:
        操作结果
    """
    import uuid
    from datetime import datetime

    existing = await db.execute(select(EmbyBlacklist).where(EmbyBlacklist.tmdb_id == tmdb_id))
    if existing.scalar_one_or_none():
        return {"success": True, "message": "已在黑名单中"}

    entry = EmbyBlacklist(
        id=str(uuid.uuid4()),
        tmdb_id=tmdb_id,
        created_at=datetime.now(UTC),
    )
    db.add(entry)
    await db.commit()
    return {"success": True, "message": "已加入黑名单"}


async def remove_blacklist_entry(db: AsyncSession, tmdb_id: int) -> dict:
    """从黑名单移除 TMDB ID。

    Args:
        db: 数据库会话
        tmdb_id: TMDB ID

    Returns:
        操作结果
    """
    result = await db.execute(select(EmbyBlacklist).where(EmbyBlacklist.tmdb_id == tmdb_id))
    entry = result.scalar_one_or_none()
    if not entry:
        return {"success": False, "message": "该条目不在黑名单中"}

    await db.delete(entry)
    await db.commit()
    return {"success": True, "message": "已移出黑名单"}


async def list_tmdb_404_items(db: AsyncSession, cd2_config=None) -> list[dict]:
    """列出 EmbyCache 中有但 TmdbCache 中无对应记录的剧集。

    这些剧集的 TMDB ID 无效（404 或从未成功查询），
    无法从 TMDB 获取任何数据。

    Args:
        db: 数据库会话
        cd2_config: CD2 配置对象（可选，用于计算 cd2_path）

    Returns:
        无 TMDB 数据的剧集列表
    """
    from sqlalchemy import text

    query = text("""
        SELECT
            e.tmdb_id,
            e.emby_series_name,
            e.emby_year,
            e.emby_path,
            e.emby_image_url,
            e.updated_at
        FROM emby_cache e
        LEFT JOIN tmdb_cache t ON e.tmdb_id = t.tmdb_id
        WHERE t.tmdb_id IS NULL
        ORDER BY e.updated_at DESC
    """)
    result = await db.execute(query)
    rows = result.all()

    items = []
    for row in rows:
        emby_path = row.emby_path
        cd2_path = None
        if emby_path and cd2_config:
            cd2_path = _emby_path_to_cd2(emby_path, cd2_config)

        items.append(
            {
                "tmdb_id": row.tmdb_id,
                "emby_series_name": row.emby_series_name,
                "emby_year": row.emby_year,
                "emby_path": emby_path,
                "cd2_path": cd2_path,
                "emby_image_url": row.emby_image_url,
                "detected_at": row.updated_at.isoformat() if row.updated_at else None,
            }
        )

    return items


def _emby_path_to_cd2(emby_path: str, cd2_config) -> str | None:
    """将 Emby 媒体路径转换为 CD2 文件系统路径。

    使用 CD2 配置中的路径前缀替换规则：
    Emby = /media/Symedia/MoviePilot/xx
    CD2  = /115open/已整理/xx

    如果配置了 path_prefix，则替换为该前缀对应的 CD2 路径。
    否则尝试已知的硬编码前缀映射。
    """
    prefix = cd2_config.path_prefix
    replacement = cd2_config.path_replacement
    if prefix and replacement:
        if emby_path.startswith(prefix):
            return emby_path.replace(prefix, replacement, 1)
        return emby_path

    # 兼容旧配置：硬编码前缀
    prefixes = ["/mnt/user/clouddrive/CloudDrive"]
    for pfx in prefixes:
        if emby_path.startswith(pfx):
            return emby_path[len(pfx) :]
    return emby_path
