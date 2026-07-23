"""Emby REST API 服务封装。

封装 Emby 的连接测试、库查询等接口。
Emby API 通过 X-Emby-Token 头鉴权。
"""

import asyncio
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http_client import http_client
from app.core.logger import init_logger
from app.models.emby_cache import EmbyCache
from app.models.tmdb_cache import TmdbCache
from app.services.tmdb import TMDBService

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
        self._user_id: str | None = None

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

    async def get_episodes(self, series_id: str, season_id: str | None = None) -> list[dict]:
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

    async def delete_item(self, item_id: str) -> dict:
        """从 Emby 删除媒体项（DELETE /Items/{id}）。

        ⚠️ 不可逆操作：Emby 会删除该媒体项及其本地文件（具体行为取决于
        Emby 服务端配置）。删除成功时 Emby 返回 204 No Content（空响应体）。

        Args:
            item_id: Emby 中的条目 ID（Series ID）

        Returns:
            成功返回 {}；失败返回 {"error": ..., "detail": ...}
        """
        url = f"{self.base_url}/Items/{item_id}"
        result = await http_client.delete(url, headers=self._headers)
        if "error" in result:
            logger.error(f"Emby 删除媒体项失败: item_id={item_id}, {result}")
        else:
            logger.info(f"Emby 删除媒体项成功: item_id={item_id}")
        return result

    async def _get_user_id(self) -> str | None:
        """获取 Emby 第一个用户的 ID（用户级 item 查询需要），结果缓存于实例。

        Returns:
            用户 ID，获取失败返回 None
        """
        if self._user_id:
            return self._user_id
        result = await http_client.get(f"{self.base_url}/Users", headers=self._headers)
        if isinstance(result, list) and result:
            self._user_id = result[0].get("Id")
        elif isinstance(result, dict) and result.get("Items"):
            self._user_id = result["Items"][0].get("Id")
        return self._user_id

    async def update_item_overview(self, item_id: str, overview: str) -> bool:
        """向 Emby 写入媒体项描述（不锁定字段）。

        Emby 更新元数据要求完整 DTO，因此采用 GET 完整 item → 修改 Overview →
        POST 回写的方式。不锁定 Overview：若 Emby 后续能从源刮削到描述则自动
        覆盖更新，刮削不到则保留本写入值（Emby 无新值时不会清空已有描述）。
        若该字段此前被锁定，会主动解除锁定。

        Args:
            item_id: Emby Series ID
            overview: 描述文本

        Returns:
            是否写入成功
        """
        user_id = await self._get_user_id()
        if not user_id:
            logger.warning(f"Emby 写入 overview 失败: 无法获取用户 ID (item_id={item_id})")
            return False
        item = await http_client.get(f"{self.base_url}/Users/{user_id}/Items/{item_id}", headers=self._headers)
        if not isinstance(item, dict) or "error" in item or not item.get("Id"):
            logger.warning(f"Emby 写入 overview 失败: 获取 item 失败 (item_id={item_id})")
            return False
        item["Overview"] = overview
        # 不锁定：解除可能存在的 Overview 锁定，交由 Emby 正常刮削维护
        locked = item.get("LockedFields") or []
        if "Overview" in locked:
            locked.remove("Overview")
            item["LockedFields"] = locked
        result = await http_client.post(f"{self.base_url}/Items/{item_id}", headers=self._headers, json=item)
        if "error" in result:
            logger.warning(f"Emby 写入 overview 失败: item_id={item_id}, {result}")
            return False
        return True

    async def backfill_overview(self, db: AsyncSession, tmdb_service: TMDBService) -> dict:
        """为缺少描述的剧集从 TMDB 补充 overview，写入 emby_cache 并同步到 Emby。

        只处理 emby_cache 中 overview 为空且有 emby_series_id 的条目；TMDB 也无
        描述的条目跳过。写入 Emby 时不锁定字段，后续 sync_cache 从 Emby 读回会
        保留该描述（Emby 刮削不到时不会清空），形成自洽。Emby 写入为
        best-effort，失败不影响本地缓存补充。

        Args:
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
            await self.update_item_overview(cache.emby_series_id, overview)
            filled += 1
        await db.commit()
        logger.info(f"Overview 回填完成: 检查 {checked}, 补充 {filled}, TMDB 无描述 {no_tmdb}")
        return {"checked": checked, "filled": filled, "no_tmdb": no_tmdb}

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
            return {item["Id"]: item["Name"] for item in result["Items"] if item.get("Id")}
        return {}

    async def _build_tmdb_library_map(self) -> dict[int, str]:
        """按媒体库逐个查询，构建 {tmdb_id: 媒体库名称} 映射。

        Emby 列表接口中 item 的 ParentId/FolderId 为空，无法反查所属库；
        路径子串匹配又因库名互为子串（如「国产」⊂「国产剧」/「国产动漫」）而不可靠，
        会把大量剧集错误归入「国产」或匹配不到。因此改为对每个媒体库用 ParentId
        精确查询其下的 Series，建立准确映射。

        Returns:
            {tmdb_id: 媒体库名称, ...}
        """
        library_map = await self._get_media_folders()
        tmdb_to_library: dict[int, str] = {}
        url = f"{self.base_url}/Items"
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
                result = await http_client.get(url, headers=self._headers, params=params)
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

    async def sync_cache(self, db: AsyncSession) -> dict:
        """同步 Emby 剧集数据到本地 emby_cache 表 — 只拉 Emby 数据。

        从 Emby 拉取所有带 TMDB ID 的剧集，批量分页查询每部剧集的实际集数，
        写入或更新 emby_cache 表（仅填充 emby_* 字段，TMDB 数据后续补充）。
        不存在的旧记录自动删除。

        Args:
            db: 数据库会话

        Returns:
            同步统计信息
        """
        # 构建 {tmdb_id: 媒体库名称} 映射（按媒体库精确查询，避免路径子串误判）
        tmdb_library_map = await self._build_tmdb_library_map()

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
            library_name = tmdb_library_map.get(tmdb_id)

            emby_image_url = (
                f"{self.base_url}/Items/{emby_id}/Images/Primary?api_key={self.api_key}" if emby_id else None
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
        logger.info(f"Emby 缓存同步完成: 更新 {len(synced_tmdb_ids)} 条, 删除 {deleted} 条")
        return {
            "synced": len(synced_tmdb_ids),
            "deleted": deleted,
        }

    async def _update_tmdb_data_internal(
        self,
        db: AsyncSession,
        tmdb_service: TMDBService,
        mode: str = "all",
        progress_callback=None,
    ) -> dict:
        """补充 TMDB 数据到 tmdb_cache（内部统一方法）。

        Args:
            db: 数据库会话
            tmdb_service: TMDB 服务实例
            mode: "subscribed" 仅已订阅 / "missing" 仅缺失 / "all" 全部
            progress_callback: 进度回调 async func(current, total)

        Returns:
            更新统计信息
        """
        today_str = date.today().isoformat()

        # 获取已订阅 ID（仅 subscribed 模式需要）
        subscribed_ids: set[int] = set()
        if mode == "subscribed":
            from app.models.subscription import Subscription

            sub_stmt = select(Subscription.tmdb_id).where(
                Subscription.media_type == "tv",
                Subscription.nf_subscribed == True,
            )
            sub_result = await db.execute(sub_stmt)
            subscribed_ids = {row[0] for row in sub_result.all()}

        # 获取所有有 emby_episode_count 的缓存记录
        stmt = select(EmbyCache).where(
            EmbyCache.emby_episode_count.isnot(None),
            EmbyCache.emby_episode_count > 0,
        )
        emby_cached = (await db.execute(stmt)).scalars().all()

        # 筛选需要刷新的
        to_update = []
        for c in emby_cached:
            if mode == "subscribed" and c.tmdb_id not in subscribed_ids:
                continue
            tc = await db.get(TmdbCache, c.tmdb_id)
            if mode == "missing":
                if tc is not None:
                    continue  # 已有则跳过
            else:
                if tc is not None and not (tc.tmdb_next_air_date and tc.tmdb_next_air_date < today_str):
                    continue  # 不需要刷新
            to_update.append(c)

        total = len(to_update)
        if total == 0:
            logger.info("TMDB 更新: 无记录需要刷新，跳过")
            return {"updated": 0, "total": 0}

        # 并发参数
        if mode == "subscribed":
            sem_count, batch_size, batch_sleep = None, total, 0
        elif mode == "missing":
            sem_count, batch_size, batch_sleep = 3, 3, 0.3
        else:
            sem_count, batch_size, batch_sleep = 5, 5, 0.5

        sem = asyncio.Semaphore(sem_count) if sem_count else None

        async def _fetch(tid: int) -> tuple[int, dict]:
            if sem:
                async with sem:
                    return await _do_fetch(tid)
            return await _do_fetch(tid)

        async def _do_fetch(tid: int) -> tuple[int, dict]:
            try:
                detail = await tmdb_service.get_tv_detail(tid)
                if detail and "error" not in detail:
                    # 复用同一份 detail 纯计算，避免对 /tv/{id} 重复发请求
                    aired = tmdb_service.aired_from_detail(detail)
                    next_date = tmdb_service.next_air_date_from_detail(detail)
                    poster = detail.get("poster_path")
                    poster_url = f"https://image.tmdb.org/t/p/w500{poster}" if poster else None
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

        async def _upsert(cache: EmbyCache, data: dict) -> bool:
            tc = await db.get(TmdbCache, cache.tmdb_id)
            if data.get("tmdb_404"):
                if tc:
                    tc.tmdb_404 = True
                else:
                    tc = TmdbCache(tmdb_id=cache.tmdb_id, tmdb_404=True)
                    db.add(tc)
                return True
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
            return True

        log_label = {"subscribed": "已订阅", "missing": "缺失补充", "all": "全量"}[mode]
        logger.info(f"TMDB {log_label}: {total} 条记录, 开始扫描...")

        updated = 0
        for i in range(0, total, batch_size):
            batch = to_update[i : i + batch_size]
            tasks = [_fetch(c.tmdb_id) for c in batch]
            results = await asyncio.gather(*tasks)
            tmdb_map = dict(results)

            for cache in batch:
                data = tmdb_map.get(cache.tmdb_id, {})
                if not data:
                    continue
                if await _upsert(cache, data):
                    updated += 1

            if progress_callback:
                await progress_callback(min(i + batch_size, total), total)

            if mode != "subscribed":
                if (i + batch_size) % (batch_size * 10) == 0 or i + batch_size >= total:
                    await db.commit()
                    logger.info(f"TMDB {log_label} 进度: {min(i + batch_size, total)}/{total}, 已更新 {updated}")
                if batch_sleep:
                    await asyncio.sleep(batch_sleep)

        await db.commit()
        logger.info(f"TMDB {log_label} 完成: 更新 {updated}/{total} 条")
        return {"updated": updated, "total": total}

    async def update_tmdb_data(self, db: AsyncSession, tmdb_service: TMDBService) -> dict:
        """补充 emby_cache 表的 TMDB 数据 — 只更新已订阅的连载剧集。"""
        return await self._update_tmdb_data_internal(db, tmdb_service, mode="subscribed")

    async def update_tmdb_data_all(
        self,
        db: AsyncSession,
        tmdb_service: TMDBService,
        progress_callback=None,
    ) -> dict:
        """补充 TMDB 数据到 tmdb_cache（不限已订阅，慢速批量）。"""
        return await self._update_tmdb_data_internal(
            db,
            tmdb_service,
            mode="all",
            progress_callback=progress_callback,
        )

    async def update_tmdb_data_missing(
        self,
        db: AsyncSession,
        tmdb_service: TMDBService,
    ) -> dict:
        """补充 tmdb_cache 缺失 TMDB 数据的记录 — 轻量增量。"""
        return await self._update_tmdb_data_internal(db, tmdb_service, mode="missing")
