"""MoviePilot REST API 服务封装。

封装 MoviePilot 的搜索、订阅与站点统计接口。
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
            logger.error(f"MoviePilot 搜索失败 (tmdb_id={tmdb_id}, type={media_type}): {result}")
        return result

    async def create_subscription(
        self,
        tmdb_id: int,
        media_type: str,
        title: str,
        year: int | None = None,
        season: int | None = None,
    ) -> dict:
        """在 MoviePilot 创建订阅。

        仅透传公共可写字段；state/lack_episode/date 等运行态字段由 MP 自行填充，
        创建时不能传（会被 to_public_write_payload 裁剪，也避免语义错误）。

        Args:
            tmdb_id: TMDB ID
            media_type: 媒体类型（movie / tv）
            title: 媒体标题
            year: 发行年份
            season: 季号（tv 必填，movie 传 None）

        Returns:
            MP 响应字典。成功时形如 ``{"success": True, "data": {"id": <sub_id>}, ...}``；
            失败时含 ``error`` 键。
        """
        url = f"{self.base_url}/api/v1/subscribe/"
        body: dict = {
            "name": title,
            "type": media_type,
            "tmdbid": tmdb_id,
        }
        if year is not None:
            body["year"] = str(year)
        if season is not None:
            body["season"] = season
        result = await http_client.post(url, headers=self._headers, json=body)
        if "error" in result:
            logger.error(
                "MoviePilot 创建订阅失败 (tmdb_id=%d, type=%s, season=%s): %s", tmdb_id, media_type, season, result
            )
        return result

    async def get_missing_seasons(
        self,
        tmdb_id: int,
        media_type: str,
        title: str,
        year: int | None = None,
    ) -> list[dict] | dict:
        """查询媒体库缺失信息 — 返回按季的缺集清单。

        调用 MP ``POST /api/v1/mediaserver/notexists``，依赖 MP 已配置的媒体服务器
        （Emby 等）。返回的每个缺集季包含 season / episodes / total_episode 等。

        Args:
            tmdb_id: TMDB ID
            media_type: 媒体类型（movie / tv）
            title: 媒体标题
            year: 发行年份

        Returns:
            成功：缺集信息列表（``NotExistMediaInfo`` 字典数组）。
            电影已入库返回 ``[]``，未入库返回 ``[{}]``（单个空对象）。
            失败：含 ``error`` 键的字典。
        """
        url = f"{self.base_url}/api/v1/mediaserver/notexists"
        body: dict = {"tmdbid": tmdb_id, "type": media_type, "title": title}
        if year is not None:
            body["year"] = str(year)
        result = await http_client.post(url, headers=self._headers, json=body)
        if "error" in result:
            logger.error("MoviePilot 查询缺集失败 (tmdb_id=%d): %s", tmdb_id, result)
            return result
        if not isinstance(result, list):
            return []
        return result

    async def get_subscription_detail(self, mp_sub_id: int) -> dict:
        """获取单条 MoviePilot 订阅详情。

        Args:
            mp_sub_id: MoviePilot 订阅 ID

        Returns:
            订阅详情字典（含 lack_episode/total_episode/state 等运行态字段）；
            失败时含 ``error`` 键。
        """
        url = f"{self.base_url}/api/v1/subscribe/{mp_sub_id}"
        result = await http_client.get(url, headers=self._headers)
        if "error" in result:
            logger.error("MoviePilot 获取订阅详情失败 (sub_id=%d): %s", mp_sub_id, result)
        return result

    async def delete_subscription(self, mp_sub_id: int) -> dict:
        """删除 MoviePilot 订阅。

        Args:
            mp_sub_id: MoviePilot 订阅 ID

        Returns:
            MP 响应字典；失败时含 ``error`` 键。
        """
        url = f"{self.base_url}/api/v1/subscribe/{mp_sub_id}"
        result = await http_client.delete(url, headers=self._headers)
        if "error" in result:
            logger.error("MoviePilot 删除订阅失败 (sub_id=%d): %s", mp_sub_id, result)
        return result

    async def find_subscription(self, tmdb_id: int, season: int | None = None) -> dict | list | None:
        """按媒体 ID 查询 MoviePilot 是否已存在订阅（防重用）。

        Args:
            tmdb_id: TMDB ID
            season: 季号（可选，tv 指定季时传入）

        Returns:
            找到返回订阅字典/列表，未找到或失败返回 None。
        """
        url = f"{self.base_url}/api/v1/subscribe/media/tmdb:{tmdb_id}"
        params = {"season": season} if season is not None else None
        result = await http_client.get(url, headers=self._headers, params=params)
        if "error" in result:
            # 404 等"不存在"视为未找到，不算错误
            return None
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
