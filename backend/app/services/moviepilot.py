"""MoviePilot REST API 服务封装。

封装 MoviePilot 的搜索与站点统计接口。
MoviePilot 的 API 返回 307 重定向，httpx 通过 follow_redirects=True 自动跟随。
"""

from app.core.http_client import http_client
from app.core.logger import init_logger

logger = init_logger()


class MoviePilotService:
    """MoviePilot REST API 客户端。

    通过 Authorization Bearer Token 鉴权，自动跟随 307 重定向。
    """

    def __init__(self, base_url: str, api_key: str):
        """初始化 MoviePilot 服务。

        Args:
            base_url: MoviePilot API 基础地址（如 http://192.168.31.10:3000）
            api_key: API Token（Bearer 鉴权）
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "accept": "application/json",
        }

    async def search_media(self, tmdb_id: int, media_type: str) -> dict:
        """调用 MoviePilot 搜索媒体资源。

        MoviePilot 可能返回 307 重定向，httpx 配置了 follow_redirects=True
        会自动跟随。

        Args:
            tmdb_id: TMDB ID
            media_type: 媒体类型（movie / tv）

        Returns:
            API 响应字典
        """
        url = f"{self.base_url}/api/v1/search/media"
        body = {"tmdbid": tmdb_id, "media_type": media_type}
        result = await http_client.post(url, headers=self._headers, json=body)
        if "error" in result:
            logger.error(
                f"MoviePilot 搜索失败 (tmdb_id={tmdb_id}, type={media_type}): {result}"
            )
        return result

    async def get_site_statistic(self) -> list[dict]:
        """获取 MoviePilot 站点统计信息。

        Returns:
            站点统计列表
        """
        url = f"{self.base_url}/api/v1/site/statistic"
        result = await http_client.get(url, headers=self._headers)
        if "error" in result:
            logger.error(f"MoviePilot 获取站点统计失败: {result}")
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("data", result.get("statistics", []))
        return []
