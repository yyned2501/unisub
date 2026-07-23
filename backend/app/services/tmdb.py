"""TMDB API 服务封装 — 获取剧集播出进度信息。

用于计算连载中剧集的实际已播出集数，避免以 TMDB 总量作为缺集基准。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http_client import http_client
from app.core.logger import init_logger

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
            logger.error(f"TMDB 请求失败 [{path}]: {result}")
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

        status = detail.get("status", "")
        if status != "Returning Series":
            return None  # 已完结的剧集直接用 TMDB 总量

        # 获取最后一集播出信息
        last = detail.get("last_episode_to_air")
        if not last:
            return None

        last_season = last.get("season_number", 0)
        last_episode = last.get("episode_number", 0)
        if last_season == 0 or last_episode == 0:
            return None

        # 累加已完结季的全集数
        total = 0
        seasons = detail.get("seasons", [])
        for s in seasons:
            sn = s.get("season_number", 0)
            if sn == 0:
                continue  # 跳过特典季
            ec = s.get("episode_count", 0) or 0
            if sn < last_season:
                total += ec

        total += last_episode
        return total

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
        next_ep = detail.get("next_episode_to_air")
        if next_ep:
            return next_ep.get("air_date")
        return None

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
                        "poster": (
                            f"https://image.tmdb.org/t/p/w500{r['poster_path']}" if r.get("poster_path") else None
                        ),
                        "poster_path": r.get("poster_path") or "",
                        "overview": r.get("overview", ""),
                        "original_language": r.get("original_language", ""),
                        "popularity": r.get("popularity", 0),
                    }
                )

        return normalized

    async def update_cache_for_tv(self, db: AsyncSession, tmdb_id: int) -> dict | None:
        """查询 TV 剧集的 TMDB 详情并写入本地缓存（tmdb_cache）。

        任何调用方（自动订阅、同步等）调此方法，查到的数据自动落库，
        后续二次使用不再需要重复调 TMDB API。

        Args:
            db: 数据库会话
            tmdb_id: TMDB ID

        Returns:
            缓存数据字典，或 None（查询失败/非 TV）
        """
        from app.models.tmdb_cache import TmdbCache

        detail = await self.get_tv_detail(tmdb_id)
        if not detail or "error" in detail:
            return None

        aired = await self.get_aired_episode_count(tmdb_id)
        next_date = await self.get_next_air_date(tmdb_id)
        poster_path = detail.get("poster_path")
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

        data = {
            "tmdb_total_eps": detail.get("number_of_episodes"),
            "tmdb_aired_eps": aired,
            "tmdb_next_air_date": next_date,
            "poster_url": poster_url,
        }

        tc = await db.get(TmdbCache, tmdb_id)
        if tc:
            tc.tmdb_total_eps = data["tmdb_total_eps"]
            tc.tmdb_aired_eps = data["tmdb_aired_eps"]
            tc.tmdb_next_air_date = data["tmdb_next_air_date"]
            if poster_url:
                tc.poster_url = poster_url
        else:
            db.add(TmdbCache(tmdb_id=tmdb_id, **data))

        try:
            await db.commit()
        except Exception:
            await db.rollback()
            logger.debug(f"TMDB 缓存写入失败: tmdb_id={tmdb_id}", exc_info=True)
            return None

        return data
