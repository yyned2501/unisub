"""Emby 缓存同步 — EmbyService 的库扫描与 emby_cache 落库逻辑。

从 emby.py 拆出：全库剧集拉取、按季集数聚合、媒体库归属映射、
UPSERT emby_cache/emby_season_cache，以及 overview 回填。
函数均接收 EmbyService 实例复用其鉴权与查询能力。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http_client import http_client
from app.core.logger import init_logger
from app.models.emby_cache import EmbyCache
from app.models.emby_season_cache import EmbySeasonCache

if TYPE_CHECKING:
    from app.services.emby import EmbyService
    from app.services.tmdb import TMDBService

logger = init_logger()


def aggregate_episodes(ep_items: list[dict]) -> tuple[dict[str, int], dict[str, dict[int, int]]]:
    """把一批 Emby Episode 项聚合为整剧集数与按季集数。

    Args:
        ep_items: Emby /Items 返回的 Episode 项列表（需含 SeriesId、ParentIndexNumber）

    Returns:
        ``(episode_counts, season_counts)``：
        episode_counts = ``{series_id: 整剧集数}``；
        season_counts = ``{series_id: {季号: 该季集数}}``（跳过无 SeriesId 的项，
        特典季 ParentIndexNumber<1 不计入按季统计）。
    """
    episode_counts: dict[str, int] = {}
    season_counts: dict[str, dict[int, int]] = {}
    for ep in ep_items:
        sid = ep.get("SeriesId")
        if not sid:
            continue
        episode_counts[sid] = episode_counts.get(sid, 0) + 1
        sn = ep.get("ParentIndexNumber")
        if sn is None:
            continue
        sn = int(sn)
        if sn < 1:
            continue  # 特典季/异常季号不计入按季统计
        per_season = season_counts.setdefault(sid, {})
        per_season[sn] = per_season.get(sn, 0) + 1
    return episode_counts, season_counts


async def get_media_folders(service: EmbyService) -> dict[str, str]:
    """获取 Emby 所有媒体库（Library Folders）的 ID 到名称的映射。

    Emby /Library/MediaFolders 返回用户有权限访问的媒体库列表，
    包含 Id 和 Name。返回 {FolderId: FolderName} 映射。

    Returns:
        {folder_id: folder_name, ...}
    """
    url = f"{service.base_url}/Library/MediaFolders"
    result = await http_client.get(url, headers=service._headers)
    if isinstance(result, dict) and result.get("Items"):
        return {item["Id"]: item["Name"] for item in result["Items"] if item.get("Id")}
    return {}


async def build_tmdb_library_map(service: EmbyService) -> dict[int, str]:
    """按媒体库逐个查询，构建 {tmdb_id: 媒体库名称} 映射。

    Emby 列表接口中 item 的 ParentId/FolderId 为空，无法反查所属库；
    路径子串匹配又因库名互为子串（如「国产」⊂「国产剧」/「国产动漫」）而不可靠，
    会把大量剧集错误归入「国产」或匹配不到。因此改为对每个媒体库用 ParentId
    精确查询其下的 Series，建立准确映射。

    Returns:
        {tmdb_id: 媒体库名称, ...}
    """
    library_map = await get_media_folders(service)
    tmdb_to_library: dict[int, str] = {}
    url = f"{service.base_url}/Items"
    limit = 5000
    for folder_id, folder_name in library_map.items():
        start_index = 0
        while True:
            params = {
                "ParentId": folder_id,
                "Recursive": "true",
                "IncludeItemTypes": "Series",
                "Fields": "ProviderIds",
                "Limit": str(limit),
                "StartIndex": str(start_index),
            }
            result = await http_client.get(url, headers=service._headers, params=params)
            if not isinstance(result, dict):
                break
            batch = result.get("Items", [])
            for it in batch:
                tmdb = (it.get("ProviderIds") or {}).get("Tmdb")
                if tmdb:
                    tmdb_to_library.setdefault(int(tmdb), folder_name)
            start_index += len(batch)
            if not batch or start_index >= int(result.get("TotalRecordCount", 0)):
                break
    return tmdb_to_library


async def sync_emby_cache(service: EmbyService, db: AsyncSession) -> dict:
    """同步 Emby 剧集数据到本地 emby_cache 表 — 只拉 Emby 数据。

    从 Emby 拉取所有带 TMDB ID 的剧集，批量分页查询每部剧集的实际集数，
    写入或更新 emby_cache 表（仅填充 emby_* 字段，TMDB 数据后续补充）。
    不存在的旧记录自动删除。

    Args:
        service: Emby 服务实例
        db: 数据库会话

    Returns:
        同步统计信息
    """
    # 构建 {tmdb_id: 媒体库名称} 映射（按媒体库精确查询，避免路径子串误判）
    tmdb_library_map = await build_tmdb_library_map(service)

    # 获取所有带 TMDB ID 的剧集
    items = await service.get_all_items_with_tmdb(
        include_item_types="Series",
        fields="ProviderIds,Path,Overview,UserData,RecursiveItemCount,ProductionYear",
    )

    # 批量分页查询所有 episode，按 SeriesId 统计整剧集数、按季集数
    # （带 ParentIndexNumber 字段，同一次请求即可拿到按季数据，零额外 Emby 调用）
    logger.info(f"Emby 缓存同步: 获取 {len(items)} 部剧集的集数统计...")
    episode_counts: dict[str, int] = {}
    season_counts: dict[str, dict[int, int]] = {}
    url = f"{service.base_url}/Items"
    limit = 50000
    start_index = 0

    while True:
        params = {
            "Recursive": "true",
            "IncludeItemTypes": "Episode",
            "Fields": "SeriesId,ParentIndexNumber",
            "Limit": str(limit),
            "StartIndex": str(start_index),
        }
        result = await http_client.get(url, headers=service._headers, params=params)
        if not isinstance(result, dict):
            break
        ep_items = result.get("Items", [])
        if not ep_items:
            break
        batch_ep, batch_season = aggregate_episodes(ep_items)
        for sid, cnt in batch_ep.items():
            episode_counts[sid] = episode_counts.get(sid, 0) + cnt
        for sid, seasons in batch_season.items():
            target = season_counts.setdefault(sid, {})
            for sn, cnt in seasons.items():
                target[sn] = target.get(sn, 0) + cnt
        total = result.get("TotalRecordCount", 0)
        start_index += len(ep_items)
        logger.info(f"  已获取 {start_index}/{total} 个 episode")
        if start_index >= total:
            break

    logger.info(f"有 episode 的剧集数: {len(episode_counts)}")

    # 写入 emby_cache（只写 emby 字段，TMDB 字段留空后续补充）
    synced_tmdb_ids = set()
    synced_season_pairs: set[tuple[int, int]] = set()

    for tmdb_id, item in items.items():
        synced_tmdb_ids.add(tmdb_id)
        emby_id = item.get("Id")
        emby_name = item.get("Name")
        emby_year = item.get("ProductionYear")
        overview = item.get("Overview")
        emby_eps = episode_counts.get(emby_id) if emby_id else None
        if emby_eps is None:
            emby_eps = item.get("RecursiveItemCount")

        # 查找该剧集所属的媒体库
        library_name = tmdb_library_map.get(tmdb_id)

        emby_image_url = f"/api/emby/image/{emby_id}" if emby_id else None
        emby_path = item.get("Path")

        # UPSERT
        stmt = select(EmbyCache).where(EmbyCache.tmdb_id == tmdb_id)
        existing = (await db.execute(stmt)).scalar_one_or_none()

        if existing:
            existing.emby_series_id = emby_id
            existing.emby_series_name = emby_name
            existing.emby_year = emby_year
            existing.emby_episode_count = emby_eps
            existing.emby_image_url = emby_image_url
            existing.overview = overview
            existing.emby_path = emby_path
            existing.emby_library_name = library_name
        else:
            cache = EmbyCache(
                tmdb_id=tmdb_id,
                emby_series_id=emby_id,
                emby_series_name=emby_name,
                emby_year=emby_year,
                emby_episode_count=emby_eps,
                emby_image_url=emby_image_url,
                overview=overview,
                emby_path=emby_path,
                emby_library_name=library_name,
            )
            db.add(cache)

        # 按季库集数写入 emby_season_cache（供 MP 订阅本地算缺集，零额外 Emby 调用）
        for sn, cnt in (season_counts.get(emby_id, {}) if emby_id else {}).items():
            synced_season_pairs.add((tmdb_id, sn))
            existing_season = await db.get(EmbySeasonCache, (tmdb_id, sn))
            if existing_season:
                existing_season.episode_count = cnt
            else:
                db.add(EmbySeasonCache(tmdb_id=tmdb_id, season=sn, episode_count=cnt))

    # 删除不再存在的旧记录（只在成功获取到 Emby 数据时执行）
    if synced_tmdb_ids:
        stmt = select(EmbyCache)
        all_cached = (await db.execute(stmt)).scalars().all()
        deleted = 0
        for cached in all_cached:
            if cached.tmdb_id not in synced_tmdb_ids:
                await db.delete(cached)
                deleted += 1
    else:
        deleted = 0
        logger.warning("Emby 缓存同步未获取到数据，跳过删除旧记录")

    # 删除按季缓存中不再存在的记录（季被删 / 剧从 Emby 移除）
    if synced_season_pairs:
        all_season_rows = (await db.execute(select(EmbySeasonCache))).scalars().all()
        for row in all_season_rows:
            if (row.tmdb_id, row.season) not in synced_season_pairs:
                await db.delete(row)

    await db.commit()
    logger.info(f"Emby 缓存同步完成: 更新 {len(synced_tmdb_ids)} 条, 删除 {deleted} 条")
    return {
        "synced": len(synced_tmdb_ids),
        "deleted": deleted,
    }


async def backfill_overview(service: EmbyService, db: AsyncSession, tmdb_service: TMDBService) -> dict:
    """为缺少描述的剧集从 TMDB 补充 overview，写入 emby_cache 并同步到 Emby。

    只处理 emby_cache 中 overview 为空且有 emby_series_id 的条目；TMDB 也无
    描述的条目跳过。写入 Emby 时不锁定字段，后续 sync_cache 从 Emby 读回会
    保留该描述（Emby 刮削不到时不会清空），形成自洽。Emby 写入为
    best-effort，失败不影响本地缓存补充。

    Args:
        service: Emby 服务实例
        db: 数据库会话
        tmdb_service: TMDB 服务实例

    Returns:
        {"checked": 检查数, "filled": 成功补充数, "no_tmdb": TMDB 无描述数}
    """
    stmt = select(EmbyCache).where(
        EmbyCache.emby_series_id.isnot(None),
        (EmbyCache.overview.is_(None)) | (EmbyCache.overview == ""),
    )
    missing = (await db.execute(stmt)).scalars().all()
    checked = len(missing)
    filled = 0
    no_tmdb = 0
    for cache in missing:
        detail = await tmdb_service.get_tv_detail(cache.tmdb_id)
        if not detail or "error" in detail:
            no_tmdb += 1
            continue
        overview = (detail.get("overview") or "").strip()
        if not overview:
            no_tmdb += 1
            continue
        cache.overview = overview
        await service.update_item_overview(cache.emby_series_id, overview)
        filled += 1
    await db.commit()
    logger.info(f"Overview 回填完成: 检查 {checked}, 补充 {filled}, TMDB 无描述 {no_tmdb}")
    return {"checked": checked, "filled": filled, "no_tmdb": no_tmdb}
