"""Emby REST API 服务封装。

封装 Emby 的连接测试、库查询等接口。
Emby API 通过 X-Emby-Token 头鉴权。

库扫描与 emby_cache 落库逻辑见 emby_cache_sync.py，
本类的 sync_cache/backfill_overview 为保持调用方不变的薄委托。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http_client import http_client
from app.core.logger import init_logger
from app.services.emby_cache_sync import backfill_overview, sync_emby_cache
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

    async def get_primary_image(self, item_id: str) -> tuple[bytes, str]:
        """获取媒体项 Primary 海报的图片字节（供代理端点转发，避免 api_key 暴露给浏览器）。

        Args:
            item_id: Emby 中的条目 ID（Series ID）

        Returns:
            (图片字节, Content-Type)

        Raises:
            HttpRequestError: Emby 请求失败
        """
        url = f"{self.base_url}/Items/{item_id}/Images/Primary"
        return await http_client.get_bytes(url, headers={"X-Emby-Token": self.api_key})

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
        """为缺少描述的剧集从 TMDB 补充 overview（委托 emby_cache_sync）。"""
        return await backfill_overview(self, db, tmdb_service)

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

    async def sync_cache(self, db: AsyncSession) -> dict:
        """同步 Emby 剧集数据到本地 emby_cache 表（委托 emby_cache_sync）。"""
        return await sync_emby_cache(self, db)

    async def update_tmdb_data(self, db: AsyncSession, tmdb_service: TMDBService) -> dict:
        """补充 emby_cache 表的 TMDB 数据 — 只更新已订阅的连载剧集。"""
        from app.services.emby_tmdb_update import update_tmdb_data_batch

        return await update_tmdb_data_batch(db, tmdb_service, mode="subscribed")

    async def update_tmdb_data_all(
        self,
        db: AsyncSession,
        tmdb_service: TMDBService,
        progress_callback=None,
    ) -> dict:
        """补充 TMDB 数据到 tmdb_cache（不限已订阅，慢速批量）。"""
        from app.services.emby_tmdb_update import update_tmdb_data_batch

        return await update_tmdb_data_batch(db, tmdb_service, mode="all", progress_callback=progress_callback)

    async def update_tmdb_data_missing(
        self,
        db: AsyncSession,
        tmdb_service: TMDBService,
    ) -> dict:
        """补充 tmdb_cache 缺失 TMDB 数据的记录 — 轻量增量。"""
        from app.services.emby_tmdb_update import update_tmdb_data_batch

        return await update_tmdb_data_batch(db, tmdb_service, mode="missing")
