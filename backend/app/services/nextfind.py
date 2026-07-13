"""NextFind OpenAPI 服务封装。

封装 NextFind 的搜索、订阅、转存、额度查询等 OpenAPI 接口。
"""

from app.core.http_client import http_client
from app.core.logger import init_logger

logger = init_logger()


class NextFindService:
    """NextFind OpenAPI 客户端。

    所有方法通过 X-API-Key 头鉴权，自动处理 JSON 解析与错误。
    """

    def __init__(self, base_url: str, api_key: str):
        """初始化 NextFind 服务。

        Args:
            base_url: NextFind API 基础地址（如 http://192.168.31.10:8092）
            api_key: OpenAPI 鉴权密钥
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._headers = {"X-API-Key": api_key, "accept": "application/json"}

    async def search_tmdb(self, query: str, media_type: str = "all") -> list[dict]:
        """搜索 TMDB 资源。

        Args:
            query: 搜索关键词
            media_type: 媒体类型（movie / tv / all）

        Returns:
            搜索结果列表
        """
        url = f"{self.base_url}/api/openapi/search"
        params = {"query": query, "type": media_type}
        result = await http_client.get(url, headers=self._headers, params=params)
        if "error" in result:
            logger.error(f"NextFind 搜索失败: {result}")
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("data", result.get("results", []))
        return []

    async def add_subscription(self, tmdb_id: int) -> dict:
        """向 NextFind 添加订阅。

        Args:
            tmdb_id: TMDB ID

        Returns:
            API 响应字典
        """
        url = f"{self.base_url}/api/openapi/subscriptions/add"
        result = await http_client.post(
            url, headers=self._headers, json={"tmdb_id": tmdb_id}
        )
        return result

    async def remove_subscription(self, tmdb_id: int) -> dict:
        """从 NextFind 取消订阅。

        Args:
            tmdb_id: TMDB ID

        Returns:
            API 响应字典
        """
        url = f"{self.base_url}/api/openapi/subscriptions/remove"
        result = await http_client.post(
            url, headers=self._headers, json={"tmdb_id": tmdb_id}
        )
        return result

    async def get_subscriptions(self) -> list[dict]:
        """获取 NextFind 所有订阅列表。

        Returns:
            订阅列表
        """
        url = f"{self.base_url}/api/openapi/subscriptions"
        result = await http_client.get(url, headers=self._headers)
        if "error" in result:
            logger.error(f"NextFind 获取订阅列表失败: {result}")
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("data", result.get("subscriptions", []))
        return []

    async def get_quota(self) -> dict:
        """获取 NextFind 积分/额度信息。

        Returns:
            额度信息字典
        """
        url = f"{self.base_url}/api/openapi/quota"
        result = await http_client.get(url, headers=self._headers)
        return result

    async def transfer(self, tmdb_id: int, target_folder: str) -> dict:
        """触发 NextFind 一键转存。

        Args:
            tmdb_id: TMDB ID
            target_folder: 目标文件夹路径

        Returns:
            API 响应字典
        """
        url = f"{self.base_url}/api/openapi/transfer"
        result = await http_client.post(
            url,
            headers=self._headers,
            json={"tmdb_id": tmdb_id, "target_folder": target_folder},
        )
        return result

    async def get_history(self) -> list[dict]:
        """获取 NextFind 转存历史记录。

        Returns:
            历史记录列表
        """
        url = f"{self.base_url}/api/openapi/history"
        result = await http_client.get(url, headers=self._headers)
        if "error" in result:
            logger.error(f"NextFind 获取历史失败: {result}")
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("data", result.get("history", []))
        return []

    async def get_directories(self, cid: str | None = None) -> list[dict]:
        """获取 NextFind 目录结构。

        Args:
            cid: 父目录 ID，None 表示根目录

        Returns:
            目录列表
        """
        url = f"{self.base_url}/api/openapi/directories"
        params = {}
        if cid:
            params["cid"] = cid
        result = await http_client.get(url, headers=self._headers, params=params)
        if "error" in result:
            logger.error(f"NextFind 获取目录失败: {result}")
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("data", result.get("directories", []))
        return []
