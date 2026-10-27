"""MoviePilot REST API 服务封装。

封装 MoviePilot 的搜索、订阅与站点统计接口。
MoviePilot 的 API 返回 307 重定向，httpx 通过 follow_redirects=True 自动跟随。
"""

import time
from collections.abc import Awaitable, Callable

from app.core.http_client import http_client
from app.core.logger import init_logger

logger = init_logger()

# 连接失败熔断参数：连续 N 次网络层连接失败后暂停调用，冷却期后半开重试
_CONN_FAIL_THRESHOLD = 5
_CONN_FAIL_COOLDOWN = 300

# UniSub 内部媒体类型（movie/tv）→ MoviePilot API 类型值。
# MP 的 MediaType 枚举认中文「电影」/「电视剧」，传英文 tv/movie 会触发
# MediaType(type) 构造异常导致 500，故请求前必须映射。
_MP_TYPE_MAP = {
    "movie": "电影",
    "tv": "电视剧",
}


def _to_mp_type(media_type: str) -> str:
    """把 UniSub 媒体类型映射成 MoviePilot 认的类型值。

    Args:
        media_type: UniSub 媒体类型（movie / tv）

    Returns:
        MP 类型值（电影 / 电视剧）；未知类型原样返回。
    """
    return _MP_TYPE_MAP.get(media_type, media_type)


class MoviePilotService:
    """MoviePilot REST API 客户端。

    通过 X-API-Key 头鉴权（MoviePilot v2 认此头，不认 Authorization: Bearer，
    后者会返回 403「token校验不通过」），自动跟随 307 重定向。
    """

    def __init__(self, base_url: str, api_key: str):
        """初始化 MoviePilot 服务。

        Args:
            base_url: MoviePilot API 基础地址（如 http://192.168.31.10:3000）
            api_key: API Token（X-API-Key 鉴权）
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._headers = {
            "X-API-Key": api_key,
            "accept": "application/json",
        }
        # 连接失败熔断状态
        self._conn_failures = 0
        self._breaker_until = 0.0

    async def _guarded(
        self,
        request_fn: Callable[..., Awaitable[dict | list]],
        url: str,
        **kwargs,
    ) -> dict | list:
        """执行请求并施加连接失败熔断。

        MP 宕机时同步循环会逐条硬试（历史上单次同步产生过 364 条连接失败日志），
        连续连接失败达到阈值后暂停调用，冷却期过后半开放行一次尝试。
        HTTP 状态码错误（服务存活）不计入熔断。

        Args:
            request_fn: http_client 的请求方法（get/post/delete 等）
            url: 请求地址
            **kwargs: 透传给请求方法的参数

        Returns:
            响应结果；熔断打开时返回 request_failed 错误字典。
        """
        if self._conn_failures >= _CONN_FAIL_THRESHOLD and time.monotonic() < self._breaker_until:
            return {"error": "request_failed", "detail": "MoviePilot 熔断中（连续连接失败），暂停调用"}

        result = await request_fn(url, headers=self._headers, **kwargs)

        if isinstance(result, dict) and result.get("error") == "request_failed":
            self._conn_failures += 1
            if self._conn_failures == _CONN_FAIL_THRESHOLD:
                self._breaker_until = time.monotonic() + _CONN_FAIL_COOLDOWN
                logger.error(
                    "MoviePilot 连续 %d 次连接失败，熔断 %d 秒",
                    self._conn_failures,
                    _CONN_FAIL_COOLDOWN,
                )
        elif self._conn_failures:
            self._conn_failures = 0

        return result

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
        result = await self._guarded(http_client.post, url, json=body)
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
        # type 用 MP 认的中文值（电影/电视剧）；并补 media_source/media_id 媒体身份，
        # 与 notexists 保持一致，避免 MP 端 MediaType 构造异常。
        body: dict = {
            "name": title,
            "type": _to_mp_type(media_type),
            "tmdbid": tmdb_id,
            "media_source": "themoviedb",
            "media_id": str(tmdb_id),
        }
        if year is not None:
            body["year"] = str(year)
        if season is not None:
            body["season"] = season
        result = await self._guarded(http_client.post, url, json=body)
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
        seasons: dict[int, list[int]] | None = None,
    ) -> list[dict] | dict:
        """查询媒体库缺失信息 — 返回按季的缺集清单。

        调用 MP ``POST /api/v1/mediaserver/notexists``，依赖 MP 已配置的媒体服务器
        （Emby 等）。返回的每个缺集季包含 season / episodes / total_episode 等。

        关键：notexists 依据请求体里的 ``seasons`` 字段（``{季号: [集号列表]}``）
        逐季比对算缺集。若不带 seasons，MP 端会尝试 recognize_media 自动补全，
        常失败而返回空。seasons 由调用方从本地 tmdb_season 缓存（或 TMDB API）
        提供，避免本服务重复访问 MP media 接口。

        Args:
            tmdb_id: TMDB ID
            media_type: 媒体类型（movie / tv）
            title: 媒体标题
            year: 发行年份
            seasons: 季集结构 ``{季号: [集号列表]}``（电视剧必传，电影可 None）

        Returns:
            成功：缺集信息列表（``NotExistMediaInfo`` 字典数组）。
            电影已入库返回 ``[]``，未入库返回 ``[{}]``（单个空对象）。
            失败：含 ``error`` 键的字典。
        """
        url = f"{self.base_url}/api/v1/mediaserver/notexists"
        # type 必须用 MP 认的中文值（电影/电视剧），否则 MediaType 构造异常返回 500。
        body: dict = {
            "tmdbid": tmdb_id,
            "type": _to_mp_type(media_type),
            "title": title,
            "media_source": "themoviedb",
            "media_id": str(tmdb_id),
        }
        if year is not None:
            body["year"] = str(year)
        # 电视剧带上季集结构，MP 据此逐季比对算缺集（键需为字符串，与 MP 格式一致）。
        if seasons:
            body["seasons"] = {str(sn): eps for sn, eps in seasons.items()}

        result = await self._guarded(http_client.post, url, json=body)
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
        result = await self._guarded(http_client.get, url)
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
        result = await self._guarded(http_client.delete, url)
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
        result = await self._guarded(http_client.get, url, params=params)
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
        result = await self._guarded(http_client.get, url)
        if "error" in result:
            logger.error(f"MoviePilot 获取站点统计失败: {result}")
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("data", result.get("statistics", []))
        return []

    async def test_connection(self) -> dict:
        """测试 MoviePilot 连通性 — 供平台设置页"测试"按钮使用。

        与 get_site_statistic 不同，本方法保留原始 error 信息，
        使调用方能区分"连接失败"和"连上了但无站点"。
        本方法有意绕过熔断，便于用户在熔断期间随时探测 MP 是否恢复。

        Returns:
            成功：``{"success": True, "sites": <站点数>}``；
            失败：含 ``error`` 键的字典。
        """
        url = f"{self.base_url}/api/v1/site/statistic"
        result = await http_client.get(url, headers=self._headers)
        if "error" in result:
            return result
        if isinstance(result, list):
            sites = result
        elif isinstance(result, dict):
            sites = result.get("data", result.get("statistics", []))
        else:
            sites = []
        return {"success": True, "sites": len(sites) if isinstance(sites, list) else 0}
