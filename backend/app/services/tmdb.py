"""TMDB API 服务封装 — 获取剧集播出进度信息。

用于计算连载中剧集的实际已播出集数，避免以 TMDB 总量作为缺集基准。
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http_client import http_client
from app.core.logger import init_logger

logger = init_logger()

# 未播季重新识别间隔：一旦识别出某季无已播集数并过滤，此间隔内不再查 TMDB 复核，
# 过期后才重新识别（届时该季可能已开播）。过滤掉的季 1 天内直接复用缓存跳过。
SEASON_CACHE_TTL = timedelta(days=1)


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
            logger.error("TMDB 请求失败 [%s]: %s", path, result)
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

        return self.aired_from_detail(detail)

    @staticmethod
    def aired_from_detail(detail: dict) -> int | None:
        """从已获取的剧集详情计算实际已播出集数（纯计算，不发请求）。

        逻辑与 get_aired_episode_count 一致，供已持有 detail 的调用方复用，
        避免对同一 /tv/{id} 端点重复发起请求。

        Args:
            detail: /tv/{id} 返回的详情字典

        Returns:
            已播出的集数，或 None（已完结/数据不足）
        """
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

    @staticmethod
    def aired_count_by_season(detail: dict) -> dict[int, int]:
        """从剧集详情计算每季已播出集数 ``{季号: 已播集数}``（纯计算，不发请求）。

        用于过滤 TMDB 脏数据：announced 但未开播的季会带 episode_count（计划总集数），
        若据此订阅会让 MP 去追根本不存在的集。此方法算出每季真实已播集数，
        已播为 0 的季不应被 MP 订阅。

        判定规则：
            - 季首播日 air_date 缺失或晚于今天 → 0（未开播）
            - 连载剧（Returning Series）：早于当前播出季的视为全部播出（=总集数）；
              当前季用 last_episode_to_air 的集号；晚于当前季的为 0
            - 其他状态（已完结/取消等）且已开播 → 视为全部播出（=总集数）

        Args:
            detail: /tv/{id} 返回的详情字典（含 seasons / status / last_episode_to_air）

        Returns:
            ``{季号: 已播集数}``，不含特典季（season_number=0）
        """
        today = datetime.now(UTC).date()
        status = detail.get("status", "")
        last = detail.get("last_episode_to_air") or {}
        last_season = last.get("season_number") or 0
        last_episode = last.get("episode_number") or 0

        result: dict[int, int] = {}
        for s in detail.get("seasons") or []:
            sn = s.get("season_number")
            if sn is None or sn == 0:
                continue  # 跳过特典季
            episode_count = s.get("episode_count") or 0
            air_date = _parse_date(s.get("air_date"))
            if air_date is None or air_date > today:
                result[sn] = 0  # 无首播日或在未来 → 未开播
                continue
            if status == "Returning Series":
                if sn < last_season:
                    result[sn] = episode_count  # 早于当前季 → 已全部播出
                elif sn == last_season:
                    result[sn] = last_episode  # 当前季 → 已播到 last_episode
                else:
                    result[sn] = 0  # 晚于当前播出季 → 未播
            else:
                result[sn] = episode_count  # 已完结/取消等：已开播即视为全部播出
        return result

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
        return self.next_air_date_from_detail(detail)

    @staticmethod
    def next_air_date_from_detail(detail: dict) -> str | None:
        """从已获取的剧集详情提取下一集播出日期（纯计算，不发请求）。

        Args:
            detail: /tv/{id} 返回的详情字典

        Returns:
            播出日期字符串（YYYY-MM-DD）或 None（已完结/无下一集）
        """
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

        # 复用同一份 detail 纯计算，避免对 /tv/{id} 重复发请求
        aired = self.aired_from_detail(detail)
        next_date = self.next_air_date_from_detail(detail)
        poster_path = detail.get("poster_path")
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

        data = {
            "tmdb_total_eps": detail.get("number_of_episodes"),
            "tmdb_aired_eps": aired,
            "tmdb_next_air_date": next_date,
            "poster_url": poster_url,
            "tmdb_poster_path": poster_path,
        }

        tc = await db.get(TmdbCache, tmdb_id)
        if tc:
            tc.tmdb_total_eps = data["tmdb_total_eps"]
            tc.tmdb_aired_eps = data["tmdb_aired_eps"]
            tc.tmdb_next_air_date = data["tmdb_next_air_date"]
            if poster_path:
                tc.tmdb_poster_path = poster_path
            if poster_url:
                tc.poster_url = poster_url
        else:
            db.add(TmdbCache(tmdb_id=tmdb_id, **data))

        # 顺手写入按季集数结构（seasons），供 MP 订阅计算缺集季复用，
        # 避免订阅同步重复访问外部接口。detail 已在手，零额外请求。
        await self._save_seasons(db, tmdb_id, detail)

        try:
            await db.commit()
        except Exception:
            await db.rollback()
            logger.debug("TMDB 缓存写入失败: tmdb_id=%d", tmdb_id, exc_info=True)
            return None

        return data

    async def _save_seasons(self, db: AsyncSession, tmdb_id: int, detail: dict) -> None:
        """把剧集详情的 seasons 按季写入 tmdb_season 表（不 commit，由调用方统一提交）。

        跳过 season_number=0 的特典季。已存在的季更新 episode_count/air_date，
        不存在的新增。

        Args:
            db: 数据库会话
            tmdb_id: TMDB ID
            detail: /tv/{id} 返回的详情字典（含 seasons 列表）
        """
        from app.models.tmdb_season import TmdbSeason

        # 先算每季已播集数（过滤未播季的依据），与季数据一并落库
        aired_map = self.aired_count_by_season(detail)
        seasons = detail.get("seasons") or []
        for s in seasons:
            sn = s.get("season_number")
            if sn is None or sn == 0:
                continue  # 跳过特典季
            episode_count = s.get("episode_count") or 0
            air_date = s.get("air_date")
            aired_count = aired_map.get(sn, 0)
            # 复合主键 (tmdb_id, season)，用 get 精确取
            existing = await db.get(TmdbSeason, (tmdb_id, sn))
            if existing:
                existing.episode_count = episode_count
                existing.aired_count = aired_count
                existing.air_date = air_date
            else:
                db.add(
                    TmdbSeason(
                        tmdb_id=tmdb_id,
                        season=sn,
                        episode_count=episode_count,
                        aired_count=aired_count,
                        air_date=air_date,
                    )
                )

    async def get_seasons_map(self, db: AsyncSession, tmdb_id: int) -> dict[int, list[int]] | None:
        """获取剧集的季集结构（{季号: [集号列表]}），优先本地缓存，缺失时调 TMDB 补。

        MP notexists 依据此结构逐季比对算缺集。本地 tmdb_season 无数据时，
        调 update_cache_for_tv 查询 TMDB 并落库（一次请求同时刷新整剧缓存与季数据）。

        过滤 TMDB 脏数据：只纳入有已播集数（aired_count>0）的季，集数范围以已播集数
        为准（[1..aired_count]），未开播的季不出现在结构中 → MP 不会对其建订阅。
        未播季的识别结果带 1 天 TTL：距上次评估超过 SEASON_CACHE_TTL 才重新拉 TMDB
        复核，1 天内直接复用缓存跳过，避免每轮同步都重查未播季。

        Args:
            db: 数据库会话
            tmdb_id: TMDB ID

        Returns:
            ``{季号: [集号列表]}``（仅含已播季）；查不到任何季数据时返回 None。
        """
        from sqlalchemy import select

        from app.models.tmdb_season import TmdbSeason

        rows = (await db.execute(select(TmdbSeason).where(TmdbSeason.tmdb_id == tmdb_id))).scalars().all()
        if not rows:
            # 本地无缓存 → 调 TMDB 查询并写入（update_cache_for_tv 内部会 _save_seasons）
            await self.update_cache_for_tv(db, tmdb_id)
            rows = (await db.execute(select(TmdbSeason).where(TmdbSeason.tmdb_id == tmdb_id))).scalars().all()

        # 有未播季且其识别结果已过 TTL → 重新拉 TMDB 复核（该季可能已开播）
        if rows and self._unaired_needs_refresh(rows):
            await self.update_cache_for_tv(db, tmdb_id)
            rows = (await db.execute(select(TmdbSeason).where(TmdbSeason.tmdb_id == tmdb_id))).scalars().all()

        if not rows:
            return None

        # 只纳入已播季，集数范围以已播集数为准
        return {row.season: list(range(1, (row.aired_count or 0) + 1)) for row in rows if (row.aired_count or 0) > 0}

    def _unaired_needs_refresh(self, rows: list) -> bool:
        """判断是否需要为未播季重新拉 TMDB 复核。

        仅当存在 aired_count=0 的季、且其上次评估（updated_at）距今超过
        SEASON_CACHE_TTL 时才刷新；否则 1 天内复用缓存，不重查未播季。

        Args:
            rows: tmdb_season 行列表

        Returns:
            需要刷新返回 True
        """
        if not self.api_key:
            return False
        now = datetime.now(UTC)
        for row in rows:
            if (row.aired_count or 0) != 0:
                continue  # 已播季不在此处触发刷新
            updated = row.updated_at
            if updated is None:
                return True
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)  # sqlite 可能返回 naive datetime
            if now - updated > SEASON_CACHE_TTL:
                return True
        return False


def _parse_date(value: str | None) -> date | None:
    """把 ``YYYY-MM-DD`` 字符串解析为 date，缺失或非法格式返回 None。

    Args:
        value: 日期字符串（TMDB 的 air_date 等，可能带时间后缀）

    Returns:
        解析出的 date，或 None
    """
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
