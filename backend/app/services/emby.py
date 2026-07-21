"""Emby REST API 服务封装。

封装 Emby 的连接测试、库查询等接口。
Emby API 通过 X-Emby-Token 头鉴权。
"""

import asyncio
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http_client import http_client
from app.core.logger import init_logger
from app.services.tmdb import TMDBService
from app.models.emby_cache import EmbyCache
from app.models.tmdb_cache import TmdbCache
from app.models.subscription import Subscription

logger = init_logger()


class EmbyService:
    """Emby REST API 客户端。

    所有方法通过 X-Emby-Token 头鉴权。
    """

    def __init__(self, base_url: str, api_key: str):
        """初始化 Emby 服务。

        Args:
            base_url: Emby 服务器地址（如 http://192.168.31.10:8096）
            api_key: X-Emby-Token 鉴权密钥
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._headers = {"X-Emby-Token": api_key, "accept": "application/json"}

    async def test_connection(self) -> dict:
        """测试 Emby 连接 — 调用 /System/Info 接口。

        Returns:
            包含服务器信息的字典，失败时包含 error 字段
        """
        url = f"{self.base_url}/System/Info"
        result = await http_client.get(url, headers=self._headers)
        if "error" in result:
            logger.error(f"Emby 连接测试失败: {result}")
        return result

    async def get_items(
        self,
        limit: int = 100,
        recursive: bool = True,
        include_item_types: str = "Movie,Series",
        fields: str = "PrimaryImageAspectRatio,UserData,Overview",
    ) -> list[dict]:
        """获取 Emby 媒体库列表。

        Args:
            limit: 返回数量上限
            recursive: 是否递归查询
            include_item_types: 媒体类型过滤（逗号分隔）
            fields: 返回字段

        Returns:
            媒体项列表
        """
        url = f"{self.base_url}/Items"
        params = {
            "Limit": limit,
            "Recursive": str(recursive).lower(),
            "IncludeItemTypes": include_item_types,
            "Fields": fields,
        }
        result = await http_client.get(url, headers=self._headers, params=params)
        if "error" in result:
            logger.error(f"Emby 获取媒体列表失败: {result}")
            return []
        if isinstance(result, dict):
            return result.get("Items", result.get("items", []))
        if isinstance(result, list):
            return result
        return []

    async def get_episodes(
        self, series_id: str, season_id: str | None = None
    ) -> list[dict]:
        """获取剧集的所有集。

        Args:
            series_id: 剧集 ID
            season_id: 季 ID（可选）

        Returns:
            剧集列表
        """
        url = f"{self.base_url}/Shows/{series_id}/Episodes"
        params: dict = {}
        if season_id:
            params["seasonId"] = season_id
        result = await http_client.get(url, headers=self._headers, params=params)
        if "error" in result:
            logger.error(f"Emby 获取剧集失败: {result}")
            return []
        if isinstance(result, dict):
            return result.get("Items", result.get("items", []))
        if isinstance(result, list):
            return result
        return []

    async def get_items_by_tmdb_id(self, tmdb_id: int) -> list[dict]:
        """通过 TMDB ID 查询 Emby 中的媒体项。

        Args:
            tmdb_id: TMDB ID

        Returns:
            匹配的媒体项列表
        """
        all_items = await self.get_items(
            limit=500,
            include_item_types="Movie,Series",
            fields="ProviderIds,PrimaryImageAspectRatio",
        )
        result = []
        for item in all_items:
            provider_ids = item.get("ProviderIds") or {}
            if str(provider_ids.get("Tmdb", "")) == str(tmdb_id):
                result.append(item)
        return result

    async def get_all_items_with_tmdb(
        self,
        include_item_types: str = "Movie,Series",
        fields: str = "ProviderIds,Path,Overview,UserData,RecursiveItemCount,ProductionYear",
    ) -> dict[int, dict]:
        """获取所有带 TMDB ID 的媒体项，按 tmdb_id 索引。

        批量查询 Emby 中所有指定类型的媒体项，提取 TMDB ID 建立索引，
        比逐条 get_items_by_tmdb_id 调用更高效。

        Args:
            include_item_types: 媒体类型过滤（逗号分隔）

        Returns:
            {tmdb_id: item_dict, ...}
        """
        items = await self.get_items(
            limit=5000,
            include_item_types=include_item_types,
            fields="ProviderIds,Path,Overview,UserData,RecursiveItemCount,ProductionYear",
        )
        result: dict[int, dict] = {}
        for item in items:
            provider_ids = item.get("ProviderIds") or {}
            tmdb_id = provider_ids.get("Tmdb")
            if tmdb_id:
                result[int(tmdb_id)] = item
        return result

    async def _get_media_folders(self) -> dict[str, str]:
        """获取 Emby 所有媒体库（Library Folders）的 ID 到名称的映射。

        Emby /Library/MediaFolders 返回用户有权限访问的媒体库列表，
        包含 Id 和 Name。返回 {FolderId: FolderName} 映射。

        Returns:
            {folder_id: folder_name, ...}
        """
        url = f"{self.base_url}/Library/MediaFolders"
        result = await http_client.get(url, headers=self._headers)
        if isinstance(result, dict) and result.get("Items"):
            return {
                item["Id"]: item["Name"]
                for item in result["Items"]
                if item.get("Id")
            }
        return {}

    def _get_library_for_item(self, item: dict, library_map: dict[str, str]) -> str | None:
        """根据 Emby item 的 FolderId 查找所属的媒体库名称。

        Args:
            item: Emby item（Series）
            library_map: _get_media_folders() 返回的映射

        Returns:
            媒体库名称，未找到时返回 None
        """
        folder_id = item.get("FolderId") or item.get("ParentId")
        if folder_id and library_map.get(folder_id):
            return library_map[folder_id]
        # 备用：通过路径前缀判断
        for _fid, fname in library_map.items():
            path = item.get("Path") or ""
            if fname in path:
                return fname
        return None

    async def sync_cache(
        self, db: AsyncSession
    ) -> dict:
        """同步 Emby 剧集数据到本地 emby_cache 表 — 只拉 Emby 数据。

        从 Emby 拉取所有带 TMDB ID 的剧集，批量分页查询每部剧集的实际集数，
        写入或更新 emby_cache 表（仅填充 emby_* 字段，TMDB 数据后续补充）。
        不存在的旧记录自动删除。

        Args:
            db: 数据库会话

        Returns:
            同步统计信息
        """
        # 获取所有媒体库（文件夹）信息
        library_map = await self._get_media_folders()

        # 获取所有带 TMDB ID 的剧集
        items = await self.get_all_items_with_tmdb(
            include_item_types="Series",
            fields="ProviderIds,Path,Overview,UserData,RecursiveItemCount,ProductionYear",
        )

        # 批量分页查询所有 episode，按 SeriesId 统计实际集数
        logger.info(f"Emby 缓存同步: 获取 {len(items)} 部剧集的集数统计...")
        episode_counts: dict[str, int] = {}
        url = f"{self.base_url}/Items"
        limit = 50000
        start_index = 0

        while True:
            params = {
                "Recursive": "true",
                "IncludeItemTypes": "Episode",
                "Fields": "SeriesId",
                "Limit": str(limit),
                "StartIndex": str(start_index),
            }
            result = await http_client.get(url, headers=self._headers, params=params)
            if not isinstance(result, dict):
                break
            ep_items = result.get("Items", [])
            if not ep_items:
                break
            for ep in ep_items:
                sid = ep.get("SeriesId")
                if sid:
                    episode_counts[sid] = episode_counts.get(sid, 0) + 1
            total = result.get("TotalRecordCount", 0)
            start_index += len(ep_items)
            logger.info(f"  已获取 {start_index}/{total} 个 episode")
            if start_index >= total:
                break

        logger.info(f"有 episode 的剧集数: {len(episode_counts)}")

        # 写入 emby_cache（只写 emby 字段，TMDB 字段留空后续补充）
        synced_tmdb_ids = set()

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
            library_name = self._get_library_for_item(item, library_map)

            emby_image_url = (
                f"{self.base_url}/Items/{emby_id}/Images/Primary?"
                f"api_key={self.api_key}"
                if emby_id
                else None
            )
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

        await db.commit()
        logger.info(
            f"Emby 缓存同步完成: 更新 {len(synced_tmdb_ids)} 条, "
            f"删除 {deleted} 条"
        )
        return {
            "synced": len(synced_tmdb_ids),
            "deleted": deleted,
        }

    async def update_tmdb_data(
        self, db: AsyncSession, tmdb_service: TMDBService
    ) -> dict:
        """补充 emby_cache 表的 TMDB 数据 — 只更新已订阅的连载剧集。

        遍历 emby_cache 中有 emby_episode_count 的剧集，检查是否为已订阅，
        并发查询 TMDB 并写回 tmdb_total_eps / tmdb_aired_eps / poster_url 等字段。

        Args:
            db: 数据库会话
            tmdb_service: TMDB 服务实例

        Returns:
            更新统计信息
        """
        from app.models.subscription import Subscription

        # 获取已订阅 tmdb_id
        sub_stmt = select(Subscription.tmdb_id).where(
            Subscription.media_type == "tv",
            Subscription.nf_subscribed == True,
        )
        sub_result = await db.execute(sub_stmt)
        subscribed_ids = {row[0] for row in sub_result.all()}

        # 获取所有有 emby_episode_count 且需要刷新 TMDB 的缓存记录
        today_str = date.today().isoformat()
        stmt = select(EmbyCache).where(
            EmbyCache.emby_episode_count.isnot(None),
            EmbyCache.emby_episode_count > 0,
        )
        cached = (await db.execute(stmt)).scalars().all()

        # 只处理已订阅的，且需要刷新的（从 TmdbCache 判断）
        to_update = []
        for c in cached:
            if c.tmdb_id not in subscribed_ids:
                continue
            # 检查是否需要刷新
            tc = await db.get(TmdbCache, c.tmdb_id)
            if tc is None:
                to_update.append(c)
            elif tc.tmdb_next_air_date and tc.tmdb_next_air_date < today_str:
                to_update.append(c)
        logger.info(
            f"TMDB 更新: 共 {len(cached)} 条有集数记录, "
            f"{len(to_update)} 条已订阅, 开始批量查询..."
        )

        async def _fetch(tid: int) -> tuple[int, dict]:
            detail = await tmdb_service.get_tv_detail(tid)
            if detail and "error" not in detail:
                aired = await tmdb_service.get_aired_episode_count(tid)
                next_date = await tmdb_service.get_next_air_date(tid)
                poster = detail.get("poster_path")
                poster_url = (
                    f"https://image.tmdb.org/t/p/w500{poster}"
                    if poster else None
                )
                return tid, {
                    "total_eps": detail.get("number_of_episodes"),
                    "aired_eps": aired,
                    "next_air_date": next_date,
                    "poster_path": poster,
                    "poster_url": poster_url,
                }
            return tid, {}

        tasks = [_fetch(c.tmdb_id) for c in to_update]
        results = await asyncio.gather(*tasks)
        tmdb_map = dict(results)

        updated = 0
        for cache in to_update:
            data = tmdb_map.get(cache.tmdb_id, {})
            if not data:
                continue
            # Upsert TmdbCache
            tc = await db.get(TmdbCache, cache.tmdb_id)
            if tc:
                tc.tmdb_total_eps = data.get("total_eps")
                tc.tmdb_aired_eps = data.get("aired_eps")
                tc.tmdb_next_air_date = data.get("next_air_date")
                tc.tmdb_poster_path = data.get("poster_path")
                tc.poster_url = data.get("poster_url")
            else:
                tc = TmdbCache(
                    tmdb_id=cache.tmdb_id,
                    tmdb_total_eps=data.get("total_eps"),
                    tmdb_aired_eps=data.get("aired_eps"),
                    tmdb_next_air_date=data.get("next_air_date"),
                    tmdb_poster_path=data.get("poster_path"),
                    poster_url=data.get("poster_url"),
                )
                db.add(tc)
            updated += 1

        await db.commit()
        logger.info(f"TMDB 数据更新完成: {updated} 条")
        return {"updated": updated}

    async def update_tmdb_data_all(
        self, db: AsyncSession, tmdb_service: TMDBService,
        progress_callback=None,
    ) -> dict:
        """补充 TMDB 数据到 tmdb_cache（不限已订阅）。

        遍历 emby_cache 中有 emby_episode_count 的剧集，检查 tmdb_cache
        是否需要刷新，用信号量控制并发逐条查询 TMDB 并写回 tmdb_cache。

        Args:
            db: 数据库会话
            tmdb_service: TMDB 服务实例
            progress_callback: 进度回调 async func(current, total)

        Returns:
            更新统计信息
        """
        today_str = date.today().isoformat()
        stmt = select(EmbyCache).where(
            EmbyCache.emby_episode_count.isnot(None),
            EmbyCache.emby_episode_count > 0,
        )
        emby_cached = (await db.execute(stmt)).scalars().all()

        # 筛选需要刷新的：tmdb_cache 中不存在 或 next_air_date 已过
        to_update = []
        for c in emby_cached:
            tc = await db.get(TmdbCache, c.tmdb_id)
            if tc is None:
                to_update.append(c)
            elif tc.tmdb_next_air_date and tc.tmdb_next_air_date < today_str:
                to_update.append(c)

        total = len(to_update)
        logger.info(f"TMDB 全量更新: 共 {total} 条记录需要刷新, 开始慢速扫描...")

        sem = asyncio.Semaphore(5)

        async def _fetch(tid: int) -> tuple[int, dict]:
            async with sem:
                try:
                    detail = await tmdb_service.get_tv_detail(tid)
                    if detail and "error" not in detail:
                        aired = await tmdb_service.get_aired_episode_count(tid)
                        next_date = await tmdb_service.get_next_air_date(tid)
                        poster = detail.get("poster_path")
                        poster_url = (
                            f"https://image.tmdb.org/t/p/w500{poster}"
                            if poster else None
                        )
                        return tid, {
                            "total_eps": detail.get("number_of_episodes"),
                            "aired_eps": aired,
                            "next_air_date": next_date,
                            "poster_path": poster,
                            "poster_url": poster_url,
                        }
                    if detail and "404" in detail.get("error", ""):
                        return tid, {"tmdb_404": True}
                except Exception:
                    pass
                return tid, {}

        # 分批提交，每批 5 个并发，批间间隔 1s
        updated = 0
        for i in range(0, total, 5):
            batch = to_update[i:i + 5]
            tasks = [_fetch(c.tmdb_id) for c in batch]
            results = await asyncio.gather(*tasks)
            tmdb_map = dict(results)

            for cache in batch:
                data = tmdb_map.get(cache.tmdb_id, {})
                if not data:
                    continue
                tc = await db.get(TmdbCache, cache.tmdb_id)
                if data.get("tmdb_404"):
                    if tc:
                        tc.tmdb_404 = True
                    else:
                        tc = TmdbCache(tmdb_id=cache.tmdb_id, tmdb_404=True)
                        db.add(tc)
                    updated += 1
                    continue
                if tc:
                    tc.tmdb_total_eps = data.get("total_eps")
                    tc.tmdb_aired_eps = data.get("aired_eps")
                    tc.tmdb_next_air_date = data.get("next_air_date")
                    tc.tmdb_poster_path = data.get("poster_path")
                    tc.poster_url = data.get("poster_url")
                else:
                    tc = TmdbCache(
                        tmdb_id=cache.tmdb_id,
                        tmdb_total_eps=data.get("total_eps"),
                        tmdb_aired_eps=data.get("aired_eps"),
                        tmdb_next_air_date=data.get("next_air_date"),
                        tmdb_poster_path=data.get("poster_path"),
                        poster_url=data.get("poster_url"),
                    )
                    db.add(tc)
                updated += 1

            if progress_callback:
                await progress_callback(min(i + 5, total), total)

            if i % 50 == 0:
                await db.commit()
                logger.info(f"TMDB 扫描进度: {min(i + 5, total)}/{total}, 已更新 {updated}")
            await asyncio.sleep(0.5)

        await db.commit()
        logger.info(f"TMDB 全量数据更新完成: {updated}/{total} 条")
        return {"updated": updated}

    async def update_tmdb_data_missing(
        self, db: AsyncSession, tmdb_service: TMDBService,
    ) -> dict:
        """补充 tmdb_cache 缺失 TMDB 数据的记录 — 轻量级，只补缺的。

        只处理 emby_episode_count > 0 但 tmdb_cache 中无对应记录的条目，
        用于定时后台增量补充，不会重复查询已有 TMDB 数据的条目。

        Args:
            db: 数据库会话
            tmdb_service: TMDB 服务实例

        Returns:
            更新统计信息
        """
        stmt = select(EmbyCache).where(
            EmbyCache.emby_episode_count.isnot(None),
            EmbyCache.emby_episode_count > 0,
        )
        emby_cached = (await db.execute(stmt)).scalars().all()

        # 只选 tmdb_cache 中不存在的
        to_update = []
        for c in emby_cached:
            tc = await db.get(TmdbCache, c.tmdb_id)
            if tc is None:
                to_update.append(c)

        total = len(to_update)
        if total == 0:
            logger.info("TMDB 缺失补充: 无缺失记录，跳过")
            return {"updated": 0, "total": 0}

        logger.info(f"TMDB 缺失补充: 共 {total} 条记录缺失 TMDB 数据")

        sem = asyncio.Semaphore(3)

        async def _fetch(tid: int) -> tuple[int, dict]:
            async with sem:
                try:
                    detail = await tmdb_service.get_tv_detail(tid)
                    if detail and "error" not in detail:
                        aired = await tmdb_service.get_aired_episode_count(tid)
                        next_date = await tmdb_service.get_next_air_date(tid)
                        poster = detail.get("poster_path")
                        poster_url = (
                            f"https://image.tmdb.org/t/p/w500{poster}"
                            if poster else None
                        )
                        return tid, {
                            "total_eps": detail.get("number_of_episodes"),
                            "aired_eps": aired,
                            "next_air_date": next_date,
                            "poster_path": poster,
                            "poster_url": poster_url,
                        }
                    if detail and "404" in detail.get("error", ""):
                        return tid, {"tmdb_404": True}
                except Exception:
                    pass
                return tid, {}

        updated = 0
        for i in range(0, total, 3):
            batch = to_update[i:i + 3]
            tasks = [_fetch(c.tmdb_id) for c in batch]
            results = await asyncio.gather(*tasks)
            tmdb_map = dict(results)

            for cache in batch:
                data = tmdb_map.get(cache.tmdb_id, {})
                if not data:
                    continue
                tc = await db.get(TmdbCache, cache.tmdb_id)
                if data.get("tmdb_404"):
                    if tc:
                        tc.tmdb_404 = True
                    else:
                        tc = TmdbCache(tmdb_id=cache.tmdb_id, tmdb_404=True)
                        db.add(tc)
                    updated += 1
                    continue
                if tc:
                    tc.tmdb_total_eps = data.get("total_eps")
                    tc.tmdb_aired_eps = data.get("aired_eps")
                    tc.tmdb_next_air_date = data.get("next_air_date")
                    tc.tmdb_poster_path = data.get("poster_path")
                    tc.poster_url = data.get("poster_url")
                else:
                    tc = TmdbCache(
                        tmdb_id=cache.tmdb_id,
                        tmdb_total_eps=data.get("total_eps"),
                        tmdb_aired_eps=data.get("aired_eps"),
                        tmdb_next_air_date=data.get("next_air_date"),
                        tmdb_poster_path=data.get("poster_path"),
                        poster_url=data.get("poster_url"),
                    )
                    db.add(tc)
                updated += 1

            if (i + 3) % 30 == 0 or i + 3 >= total:
                await db.commit()
                logger.info(f"TMDB 缺失补充进度: {min(i + 3, total)}/{total}, 已更新 {updated}")

            await asyncio.sleep(0.3)

        await db.commit()
        logger.info(f"TMDB 缺失补充完成: 更新 {updated}/{total} 条")
        return {"updated": updated, "total": total}