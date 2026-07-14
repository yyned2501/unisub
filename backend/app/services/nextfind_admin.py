"""NextFind 管理类 API 服务封装。

封装 NextFind 的媒体删除、历史管理、系统日志和设置等管理类 OpenAPI 接口。
"""

from urllib.parse import urlencode

from app.core.http_client import http_client
from app.core.logger import init_logger

logger = init_logger()


class NextFindAdminService:
    """NextFind 管理 API 客户端。

    封装媒体删除、历史清理、系统日志和各类设置接口。
    所有方法通过 X-API-Key 头鉴权。
    """

    def __init__(self, base_url: str, api_key: str):
        """初始化 NextFind 管理服务。

        Args:
            base_url: NextFind API 基础地址（如 http://192.168.31.10:8092）
            api_key: OpenAPI 鉴权密钥
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._headers = {"X-API-Key": api_key, "accept": "application/json"}

    # === 媒体删除 ===

    async def delete_episode(self, tmdb_id: int, season: int, episode: int) -> dict:
        """静默删除指定集。

        从网盘删除指定剧集的对应集文件。

        Args:
            tmdb_id: TMDB ID
            season: 季号
            episode: 集号

        Returns:
            API 响应字典
        """
        params = urlencode(
            {"tmdb_id": tmdb_id, "season": season, "episode": episode}
        )
        url = f"{self.base_url}/api/openapi/media/episode?{params}"
        result = await http_client.delete(url, headers=self._headers)
        if "error" in result:
            logger.error(f"NextFind 删除剧集失败: {result}")
            return {}
        return result

    async def delete_season(self, tmdb_id: int, season: int) -> dict:
        """静默删除整季。

        从网盘删除指定剧集的整季文件。

        Args:
            tmdb_id: TMDB ID
            season: 季号

        Returns:
            API 响应字典
        """
        params = urlencode({"tmdb_id": tmdb_id, "season": season})
        url = f"{self.base_url}/api/openapi/media/season?{params}"
        result = await http_client.delete(url, headers=self._headers)
        if "error" in result:
            logger.error(f"NextFind 删除整季失败: {result}")
            return {}
        return result

    async def delete_movie(self, tmdb_id: int) -> dict:
        """静默删除电影。

        从网盘删除指定电影文件。

        Args:
            tmdb_id: TMDB ID

        Returns:
            API 响应字典
        """
        params = urlencode({"tmdb_id": tmdb_id})
        url = f"{self.base_url}/api/openapi/media/movie?{params}"
        result = await http_client.delete(url, headers=self._headers)
        if "error" in result:
            logger.error(f"NextFind 删除电影失败: {result}")
            return {}
        return result

    # === 系统日志 ===

    async def get_logs(self) -> list[dict]:
        """获取系统日志。

        Returns:
            系统日志列表
        """
        url = f"{self.base_url}/api/openapi/logs"
        result = await http_client.get(url, headers=self._headers)
        if "error" in result:
            logger.error(f"NextFind 获取日志失败: {result}")
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("data", result.get("logs", []))
        return []

    # === 历史管理 ===

    async def delete_history_all(self) -> dict:
        """清空全部转存历史。

        Returns:
            API 响应字典
        """
        url = f"{self.base_url}/api/openapi/history/all"
        result = await http_client.delete(url, headers=self._headers)
        if "error" in result:
            logger.error(f"NextFind 清空历史失败: {result}")
            return {}
        return result

    async def delete_history_item(
        self, tmdb_id: int | None = None, title: str | None = None,
    ) -> dict:
        """删除特定历史记录。

        可通过 tmdb_id 或 title 精准删除对应历史记录，两者至少提供一个。

        Args:
            tmdb_id: TMDB ID（可选）
            title: 媒体标题（可选）

        Returns:
            API 响应字典
        """
        params_dict: dict = {}
        if tmdb_id is not None:
            params_dict["tmdb_id"] = tmdb_id
        if title is not None:
            params_dict["title"] = title
        params = urlencode(params_dict)
        url = f"{self.base_url}/api/openapi/history/item?{params}"
        result = await http_client.delete(url, headers=self._headers)
        if "error" in result:
            logger.error(f"NextFind 删除历史记录失败: {result}")
            return {}
        return result

    # === TG 频道设置 ===

    async def get_tg_channels(self) -> list[dict]:
        """获取 TG 频道列表。

        Returns:
            TG 频道列表
        """
        url = f"{self.base_url}/api/openapi/settings/tg_channels"
        result = await http_client.get(url, headers=self._headers)
        if "error" in result:
            logger.error(f"NextFind 获取 TG 频道失败: {result}")
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("data", result.get("channels", []))
        return []

    async def update_tg_channels(self, data: list[dict]) -> dict:
        """修改 TG 频道配置。

        Args:
            data: TG 频道配置列表

        Returns:
            API 响应字典
        """
        url = f"{self.base_url}/api/openapi/settings/tg_channels"
        result = await http_client.post(
            url, headers=self._headers, json=data
        )
        if "error" in result:
            logger.error(f"NextFind 修改 TG 频道失败: {result}")
            return {}
        return result

    # === RSS 设置 ===

    async def get_rss(self) -> list[dict]:
        """获取 RSS 订阅源列表。

        Returns:
            RSS 订阅源列表
        """
        url = f"{self.base_url}/api/openapi/settings/rss"
        result = await http_client.get(url, headers=self._headers)
        if "error" in result:
            logger.error(f"NextFind 获取 RSS 失败: {result}")
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("data", result.get("rss", []))
        return []

    async def update_rss(self, data: list[dict]) -> dict:
        """修改 RSS 订阅源配置。

        Args:
            data: RSS 订阅源配置列表

        Returns:
            API 响应字典
        """
        url = f"{self.base_url}/api/openapi/settings/rss"
        result = await http_client.post(
            url, headers=self._headers, json=data
        )
        if "error" in result:
            logger.error(f"NextFind 修改 RSS 失败: {result}")
            return {}
        return result

    # === 规则与目录设置 ===

    async def update_rules(self, data: dict) -> dict:
        """修改资源过滤规则。

        Args:
            data: 过滤规则配置

        Returns:
            API 响应字典
        """
        url = f"{self.base_url}/api/openapi/settings/rules"
        result = await http_client.post(
            url, headers=self._headers, json=data
        )
        if "error" in result:
            logger.error(f"NextFind 修改规则失败: {result}")
            return {}
        return result

    async def update_transfer_folder(self, folder: str) -> dict:
        """修改默认转存目录。

        Args:
            folder: 默认转存目录路径

        Returns:
            API 响应字典
        """
        url = f"{self.base_url}/api/openapi/settings/transfer_folder"
        result = await http_client.post(
            url, headers=self._headers,
            json={"folder": folder},
        )
        if "error" in result:
            logger.error(f"NextFind 修改转存目录失败: {result}")
            return {}
        return result
