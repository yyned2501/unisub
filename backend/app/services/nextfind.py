"""NextFind OpenAPI 服务封装。

封装 NextFind 的搜索、订阅、转存、额度查询等 OpenAPI 接口。
"""

from app.core.http_client import http_client
from app.core.logger import init_logger

logger = init_logger()

# NextFind type 映射：前端传的英文类型 → NextFind 中文类型
_TYPE_MAP = {
    "movie": "电影",
    "tv": "剧集",
    "all": "全部",
}


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
        # 将英文类型映射为 NextFind 所需的中文类型
        mapped_type = _TYPE_MAP.get(media_type, media_type)
        url = f"{self.base_url}/api/openapi/search"
        params = {"query": query, "type": mapped_type}
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

    async def search_resources(
        self, tmdb_id: int, media_type: str = "movie",
        season: int | None = None, episode: int | None = None,
    ) -> list[dict]:
        """搜索网盘与种子资源，获取标签、神盾标志、洗版权重等属性。

        Args:
            tmdb_id: TMDB ID
            media_type: 媒体类型（movie / tv）
            season: 季号
            episode: 集号

        Returns:
            资源列表
        """
        url = f"{self.base_url}/api/openapi/resources/search"
        params: dict = {"tmdb_id": tmdb_id, "media_type": media_type}
        if season is not None:
            params["season"] = season
        if episode is not None:
            params["episode"] = episode
        result = await http_client.get(url, headers=self._headers, params=params)
        if "error" in result:
            logger.error(f"NextFind 资源搜索失败: {result}")
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("data", result.get("results", []))
        return []

    async def trigger_preview(self, slug: str) -> dict:
        """触发探针解包，提取隐藏属性、探针缓存和文件树。

        Args:
            slug: 资源原始链接或标识

        Returns:
            API 响应字典
        """
        url = f"{self.base_url}/api/openapi/preview"
        result = await http_client.post(
            url, headers=self._headers, json={"slug": slug}
        )
        if "error" in result:
            logger.error(f"NextFind 探针解包失败: {result}")
            return {}
        return result

    async def hdhive_unlock(self, resource_id: str, resource_type: str) -> dict:
        """HDHive 积分解锁，消耗积分获取资源真实下载链接。

        Args:
            resource_id: 资源 ID
            resource_type: 资源类型

        Returns:
            API 响应字典
        """
        url = f"{self.base_url}/api/openapi/hdhive/unlock"
        result = await http_client.post(
            url, headers=self._headers,
            json={"id": resource_id, "type": resource_type},
        )
        if "error" in result:
            logger.error(f"NextFind HDHive 解锁失败: {result}")
            return {}
        return result

    async def create_directory(self, parent_cid: str, name: str) -> dict:
        """创建网盘目录。

        Args:
            parent_cid: 父目录 CID
            name: 新目录名称

        Returns:
            API 响应字典
        """
        url = f"{self.base_url}/api/openapi/directories"
        result = await http_client.post(
            url, headers=self._headers,
            json={"parent_cid": parent_cid, "name": name},
        )
        if "error" in result:
            logger.error(f"NextFind 创建目录失败: {result}")
            return {}
        return result

    async def filter_local_library(self, status_filter: str = "missing") -> list[dict]:
        """过滤本地库状态。

        Args:
            status_filter: 状态过滤器（missing / error / duplicate）

        Returns:
            过滤结果列表
        """
        url = f"{self.base_url}/api/openapi/local_library/filter"
        params = {"status_filter": status_filter}
        result = await http_client.get(url, headers=self._headers, params=params)
        if "error" in result:
            logger.error(f"NextFind 本地库过滤失败: {result}")
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("data", result.get("results", []))
        return []

    async def get_subscriptions_info(self, subscription_ids: list[int]) -> dict:
        """批量查询订阅的入库详情和进度。

        Args:
            subscription_ids: 订阅 ID 列表

        Returns:
            订阅详情字典
        """
        url = f"{self.base_url}/api/openapi/subscriptions/info"
        result = await http_client.post(
            url, headers=self._headers, json={"ids": subscription_ids}
        )
        if "error" in result:
            logger.error(f"NextFind 查询订阅详情失败: {result}")
            return {}
        return result

    async def fill_missing(self, tmdb_id: int, media_type: str = "tv") -> dict:
        """触发补缺集搜索，推入高优搜索队列。

        Args:
            tmdb_id: TMDB ID
            media_type: 媒体类型（movie / tv）

        Returns:
            API 响应字典
        """
        url = f"{self.base_url}/api/openapi/media/fill_missing"
        result = await http_client.post(
            url, headers=self._headers,
            json={"tmdb_id": tmdb_id, "media_type": media_type},
        )
        if "error" in result:
            logger.error(f"NextFind 补缺集搜索失败: {result}")
            return {}
        return result

    async def toggle_ignored_episode(self, tmdb_id: int, season: int) -> dict:
        """切换忽略季状态。

        Args:
            tmdb_id: TMDB ID
            season: 季号

        Returns:
            API 响应字典
        """
        url = f"{self.base_url}/api/openapi/ignored_episodes/toggle"
        result = await http_client.post(
            url, headers=self._headers,
            json={"tmdb_id": tmdb_id, "season": season},
        )
        if "error" in result:
            logger.error(f"NextFind 切换忽略季失败: {result}")
            return {}
        return result
