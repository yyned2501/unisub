"""TMDB API 服务封装 — 获取剧集播出进度信息。

用于计算连载中剧集的实际已播出集数，避免以 TMDB 总量作为缺集基准。

详情纯计算见 tmdb_detail.py；tmdb_cache / tmdb_season 的写库与季结构
读取见 tmdb_cache.py，本类同名方法为保持调用方不变的薄委托。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http_client import http_client
from app.core.logger import init_logger
from app.services.poster import build_tmdb_poster_url
from app.services.tmdb.cache import get_season_completion, get_seasons_map, update_cache_for_tv
from app.services.tmdb.detail import aired_from_detail, next_air_date_from_detail

logger = init_logger()


class TMDBService:
    """TMDB API v3 客户端，通过 api_key 查询参数鉴权。"""

    def __init__(self, api_key: str, base_url: str = "https://api.themoviedb.org/3"):
        """初始化 TMDB 服务。

        Args:
            api_key: TMDB API Key (v3 auth)
            base_url: TMDB API 基础地址，默认 https://api.themoviedb.org/3
        """
        # 统一处理 /3 前缀：base_url 不含 /3 时自动补上
        self.base_url = base_url.rstrip("/")
        if not self.base_url.endswith("/3"):
            self.base_url = f"{self.base_url}/3"
        self.api_key = api_key

    async def _get(self, path: str, params: dict | None = None) -> dict:
        """发送带 api_key 的 GET 请求。

        Args:
            path: API 路径（如 /tv/123）
            params: 额外查询参数

        Returns:
            解析后的 JSON 字典
        """
        url = f"{self.base_url}{path}"
        query_params = {"api_key": self.api_key}
        if params:
            query_params.update(params)
        result = await http_client.get(url, params=query_params)
        if "error" in result:
            # 只记 path 与错误码：result 里的 detail 含完整 URL + api_key，
            # 一旦落盘等于把 TMDB 密钥写到日志里（历史事故，勿回退）。
            logger.error("TMDB 请求失败 [%s]: %s", path, result.get("error"))
        return result

    async def get_aired_episode_count(self, tmdb_id: int) -> int | None:
        """获取剧集实际已播出的集数。

        对于连载中的剧集（Returning Series），根据 last_episode_to_air
        累加已完成季的全集数 + 当前季已播集数。
        对于已完结/单次剧集，返回 None 表示使用 TMDB 总量即可。

        Args:
            tmdb_id: TMDB ID

        Returns:
            已播出的集数，或 None（无需调整/获取失败）
        """
        if not self.api_key:
            return None

        detail = await self._get(f"/tv/{tmdb_id}")
        if "error" in detail or not detail:
            return None

        return aired_from_detail(detail)

    async def get_tv_detail(self, tmdb_id: int) -> dict:
        """获取剧集完整详情，包括 number_of_episodes、seasons 等。

        Args:
            tmdb_id: TMDB ID

        Returns:
            剧集详情字典
        """
        return await self._get(f"/tv/{tmdb_id}")

    async def get_next_air_date(self, tmdb_id: int) -> str | None:
        """获取剧集的下一集播出日期。

        Args:
            tmdb_id: TMDB ID

        Returns:
            播出日期字符串（YYYY-MM-DD）或 None（已完结/获取失败）
        """
        if not self.api_key:
            return None
        detail = await self._get(f"/tv/{tmdb_id}")
        if "error" in detail or not detail:
            return None
        return next_air_date_from_detail(detail)

    async def get_movie_detail(self, tmdb_id: int) -> dict:
        """获取电影详情。

        Args:
            tmdb_id: TMDB ID

        Returns:
            电影详情字典
        """
        return await self._get(f"/movie/{tmdb_id}")

    async def search(self, query: str, media_type: str = "all") -> list[dict]:
        """搜索 TMDB 资源。

        分别调用 /search/movie 和 /search/tv（tmdbapi 代理的显式端点），
        返回标准化结果列表，字段与 NextFind 搜索返回格式对齐。

        Args:
            query: 搜索关键词
            media_type: 媒体类型（movie / tv / all）

        Returns:
            标准化搜索结果列表
        """
        if not query or not query.strip():
            return []

        query = query.strip()
        normalized: list[dict] = []

        # tmdbapi 代理只显式支持 /search/movie 和 /search/tv，分两次调用
        endpoints = []
        if media_type in ("all", "movie"):
            endpoints.append(("movie", "/search/movie"))
        if media_type in ("all", "tv"):
            endpoints.append(("tv", "/search/tv"))

        for rtype, endpoint in endpoints:
            raw = await self._get(
                endpoint,
                params={
                    "query": query,
                    "language": "zh-CN",
                    "page": 1,
                },
            )
            if "error" in raw or not raw:
                continue

            for r in raw.get("results", []):
                title = r.get("title") or r.get("name") or ""
                if not title:
                    continue

                normalized.append(
                    {
                        "id": r["id"],
                        "title": title,
                        "name": r.get("name") or r.get("title", ""),
                        "media_type": rtype,
                        "raw_type": rtype,
                        "vote_average": r.get("vote_average", 0),
                        "year": (r.get("release_date") or r.get("first_air_date") or "")[:4],
                        "poster": build_tmdb_poster_url(r.get("poster_path")),
                        "poster_path": r.get("poster_path") or "",
                        "overview": r.get("overview", ""),
                        "original_language": r.get("original_language", ""),
                        "popularity": r.get("popularity", 0),
                    }
                )

        return normalized

    async def update_cache_for_tv(self, db: AsyncSession, tmdb_id: int) -> dict | None:
        """查询 TV 剧集的 TMDB 详情并写入本地缓存（委托 tmdb_cache）。"""
        return await update_cache_for_tv(self, db, tmdb_id)

    async def get_seasons_map(self, db: AsyncSession, tmdb_id: int) -> dict[int, list[int]] | None:
        """获取剧集的季集结构，优先本地缓存（委托 tmdb_cache）。"""
        return await get_seasons_map(self, db, tmdb_id)

    async def get_season_completion(self, db: AsyncSession, tmdb_id: int) -> dict[int, bool]:
        """返回每季是否已完结，依据本地缓存（委托 tmdb_cache）。"""
        return await get_season_completion(db, tmdb_id)
