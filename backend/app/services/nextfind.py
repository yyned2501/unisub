"""NextFind OpenAPI 服务封装。

封装 NextFind 的搜索、订阅、转存、额度查询等 OpenAPI 接口。
"""

from dataclasses import dataclass

from app.core.http_client import http_client
from app.core.logger import init_logger

logger = init_logger()


@dataclass(frozen=True)
class SubscriptionCreateResult:
    """NextFind 创建订阅的语义化结果。"""

    outcome: str
    subscription_id: str | None = None
    message: str = ""


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

    def _check(self, result: dict, empty: list | dict, context: str) -> list | dict | None:
        """检查 http_client 返回是否包含错误，出错时记录日志并返回空值。

        Args:
            result: http_client 返回的字典
            empty: 出错时的默认返回（[] 或 {}）
            context: 日志上下文描述（如"搜索"、"获取订阅列表"）

        Returns:
            empty 表示出错，None 表示正常
        """
        if isinstance(result, dict) and "error" in result:
            logger.error("NextFind %s 失败: %s", context, result)
            return empty
        return None

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
        if (ret := self._check(result, [], "搜索")) is not None:
            return ret
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("data", result.get("results", []))
        return []

    async def add_subscription(self, tmdb_id: int, media_type: str = "tv") -> dict:
        """向 NextFind 添加订阅。

        Args:
            tmdb_id: TMDB ID
            media_type: 媒体类型（movie / tv）

        Returns:
            API 响应字典
        """
        url = f"{self.base_url}/api/openapi/subscriptions/add"
        result = await http_client.post(
            url,
            headers=self._headers,
            json={"tmdb_id": str(tmdb_id), "media_type": media_type},
        )
        return result

    async def create_subscription(self, tmdb_id: int, media_type: str = "tv") -> SubscriptionCreateResult:
        """创建订阅并严格校验 NextFind 的业务响应。

        Args:
            tmdb_id: TMDB ID。
            media_type: 媒体类型（movie / tv）。

        Returns:
            语义化的创建结果；仅明确成功或已存在才返回成功 outcome。
        """
        result = await self.add_subscription(tmdb_id, media_type)
        if not isinstance(result, dict):
            return SubscriptionCreateResult("failed", message="NextFind 返回格式无效")

        if result.get("error"):
            return SubscriptionCreateResult("failed", message=str(result.get("detail") or result["error"]))

        status = str(result.get("status", "")).lower()
        message = str(result.get("message") or result.get("detail") or "")
        subscription_id = result.get("id") or result.get("sub_id")
        normalized_message = message.lower()
        if status in {"success", "ok", "created"}:
            return SubscriptionCreateResult(
                "created",
                subscription_id=str(subscription_id) if subscription_id else None,
                message=message,
            )
        if status in {"exists", "already_exists", "already_subscribed"} or any(
            token in normalized_message for token in ("already", "exists", "已存在", "已订阅")
        ):
            return SubscriptionCreateResult(
                "already_exists",
                subscription_id=str(subscription_id) if subscription_id else None,
                message=message,
            )

        logger.error(
            "NextFind 创建订阅业务失败: tmdb_id=%s, media_type=%s, status=%s, message=%s",
            tmdb_id,
            media_type,
            status or "missing",
            message or "响应缺少成功状态",
        )
        return SubscriptionCreateResult("failed", message=message or "NextFind 未确认订阅成功")

    async def remove_subscription(self, tmdb_id: int, media_type: str = "tv") -> dict:
        """从 NextFind 取消订阅。

        Args:
            tmdb_id: TMDB ID
            media_type: 媒体类型（movie / tv）

        Returns:
            API 响应字典
        """
        url = f"{self.base_url}/api/openapi/subscriptions/remove"
        result = await http_client.post(
            url,
            headers=self._headers,
            json={"tmdb_id": str(tmdb_id), "media_type": media_type},
        )
        return result

    async def get_subscriptions(self) -> list[dict]:
        """获取 NextFind 所有订阅列表。

        Returns:
            订阅列表
        """
        url = f"{self.base_url}/api/openapi/subscriptions"
        result = await http_client.get(url, headers=self._headers)
        if (ret := self._check(result, [], "获取订阅列表")) is not None:
            return ret
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
        if (ret := self._check(result, [], "获取历史")) is not None:
            return ret
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
        if (ret := self._check(result, [], "获取目录")) is not None:
            return ret
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("data", result.get("directories", []))
        return []

    async def search_resources(
        self,
        tmdb_id: int,
        media_type: str = "movie",
        season: int | None = None,
        episode: int | None = None,
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
        if (ret := self._check(result, [], "资源搜索")) is not None:
            return ret
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
        result = await http_client.post(url, headers=self._headers, json={"slug": slug})
        if (ret := self._check(result, {}, "探针解包")) is not None:
            return ret
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
            url,
            headers=self._headers,
            json={"id": resource_id, "type": resource_type},
        )
        if (ret := self._check(result, {}, "HDHive 解锁")) is not None:
            return ret
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
            url,
            headers=self._headers,
            json={"parent_cid": parent_cid, "name": name},
        )
        if (ret := self._check(result, {}, "创建目录")) is not None:
            return ret
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
        if (ret := self._check(result, [], "本地库过滤")) is not None:
            return ret
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("data", result.get("results", []))
        return []

    async def get_subscriptions_info(self, items: list[dict]) -> dict:
        """批量查询订阅的入库详情和进度。

        Args:
            items: 查询项列表，每项为 {"tmdb_id": str, "media_type": "tv"|"movie"}

        Returns:
            订阅详情字典，data 数组含 local_episodes / total_episodes / is_in_library 等
        """
        url = f"{self.base_url}/api/openapi/subscriptions/info"
        result = await http_client.post(url, headers=self._headers, json={"items": items})
        if (ret := self._check(result, {}, "查询订阅详情")) is not None:
            return ret
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
            url,
            headers=self._headers,
            json={"tmdb_id": str(tmdb_id), "media_type": media_type},
        )
        if (ret := self._check(result, {}, "补缺集搜索")) is not None:
            return ret
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
            url,
            headers=self._headers,
            json={"tmdb_id": str(tmdb_id), "season": season},
        )
        if (ret := self._check(result, {}, "切换忽略季")) is not None:
            return ret
        return result
