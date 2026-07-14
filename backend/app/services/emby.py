"""Emby REST API 服务封装。

封装 Emby 的连接测试、库查询等接口。
Emby API 通过 X-Emby-Token 头鉴权。
"""

from app.core.http_client import http_client
from app.core.logger import init_logger

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