"""NextFind OpenAPI 服务封装。

封装 NextFind 的搜索、订阅、转存、额度查询等 OpenAPI 接口。
"""

from dataclasses import dataclass

from app.core.http_client import http_client
from app.core.logger import init_logger

logger = init_logger()


class NextFindAuthError(Exception):
    """NextFind 鉴权失败（401/403）：API 密钥无效或已过期。运行时据此立即中止整轮。"""


class NextFindError(Exception):
    """NextFind 请求/响应异常。"""


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

    @staticmethod
    def _raise_on_auth_error(result) -> None:
        """若 http_client 返回 401/403 鉴权错误则抛 NextFindAuthError，供调用方中止整轮。"""
        if isinstance(result, dict) and result.get("error"):
            code = str(result.get("error", ""))
            if "401" in code or "403" in code:
                raise NextFindAuthError("NextFind 鉴权失败（HTTP 401/403）：API 密钥无效或已过期")

    async def search_tmdb(self, query: str, media_type: str = "all") -> list[dict]:
        """搜索 TMDB 资源。

        Args:
            query: 搜索关键词
            media_type: 媒体类型（movie / tv / all）

        Returns:
            搜索结果列表
        """
        mapped_type = _TYPE_MAP.get(media_type, media_type)
        url = f"{self.base_url}/api/openapi/search"
        params = {"query": query, "type": mapped_type}
        result = await http_client.get(url, headers=self._headers, params=params)
        self._raise_on_auth_error(result)
        if (ret := self._check(result, [], "搜索")) is not None:
            return ret
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("data", result.get("results", []))
        return []

    async def add_subscription(self, tmdb_id: int, media_type: str = "tv", title: str | None = None) -> dict:
        """向 NextFind 添加订阅。

        Args:
            tmdb_id: TMDB ID
            media_type: 媒体类型（movie / tv）
            title: 可选，辅助标题

        Returns:
            API 响应字典
        """
        body: dict = {"tmdb_id": str(tmdb_id), "media_type": media_type}
        if title:
            body["title"] = title
        url = f"{self.base_url}/api/openapi/subscriptions/add"
        result = await http_client.post(
            url,
            headers=self._headers,
            json=body,
        )
        self._raise_on_auth_error(result)
        return result

    async def create_subscription(
        self, tmdb_id: int, media_type: str = "tv", title: str | None = None
    ) -> SubscriptionCreateResult:
        """创建订阅并严格校验 NextFind 的业务响应。

        Args:
            tmdb_id: TMDB ID。
            media_type: 媒体类型（movie / tv）。

        Returns:
            语义化的创建结果；仅明确成功或已存在才返回成功 outcome。
        """
        result = await self.add_subscription(tmdb_id, media_type, title=title)
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
