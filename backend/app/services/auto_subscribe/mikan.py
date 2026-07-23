"""自动订阅 — Mikan 新番源。"""

from __future__ import annotations

import asyncio
import html
import re
from datetime import date

import httpx

from app.core.logger import init_logger
from app.services.auto_subscribe.base import RankProvider, register
from app.services.auto_subscribe.models import RankMediaItem

logger = init_logger(__name__)

MIKAN_BASE_URLS = ["https://mikanani.me", "https://mikanime.tv"]
REQUEST_TIMEOUT = 30
DETAIL_SLEEP = 0.6
BGM_ID_RE = re.compile(r"bangumi\.tv/subject/(\d+)")
YEAR_RE = re.compile(r"(19\d\d|20\d\d)")
SEASON_MAP = {"春": 1, "夏": 2, "秋": 3, "冬": 4}
SEASON_NAMES = ["春", "夏", "秋", "冬"]

# 缓存 _find_available_base 的结果，避免每次详情页都重新请求
_available_base_cache: str | None = None
_available_base_lock = asyncio.Lock()


@register
class MikanRankProvider(RankProvider):
    """Mikan 新番来源。"""

    provider_id = "mikan"
    provider_name = "Mikan 新番"

    async def fetch_async(self, options: dict) -> list[RankMediaItem]:
        """抓取 Mikan 当前季新番。"""
        season = options.get("mikan_season", "当前")
        year = options.get("mikan_year", 0) or 0
        resolve_detail = options.get("mikan_resolve_detail", True)

        if season == "当前" or not year:
            today = date.today()
            year = year or today.year
            if season == "当前":
                month = today.month
                if month <= 3:
                    season = "冬"
                elif month <= 6:
                    season = "春"
                elif month <= 9:
                    season = "夏"
                else:
                    season = "秋"

        items = await self._fetch_anime_list(year, season)
        logger.info(f"[Mikan] 抓取到 {len(items)} 部新番 ({year} {season})")

        if resolve_detail and items:
            sem = asyncio.Semaphore(5)

            async def _resolve_with_sem(item: RankMediaItem):
                async with sem:
                    try:
                        await self._resolve_detail(item)
                    except Exception as e:
                        logger.debug(f"[Mikan] 详情解析失败: {item.title}: {e}")

            await asyncio.gather(*[_resolve_with_sem(item) for item in items])

        return items

    async def _fetch_anime_list(self, year: int, season: str) -> list[RankMediaItem]:
        """从 Mikan 获取新番列表。"""
        base_url = await self._find_available_base()
        if not base_url:
            logger.error("[Mikan] 所有基础 URL 均不可用")
            return []

        url = f"{base_url}/Home/BangumiCoverFlowByDayOfWeek"
        params = {"year": year, "seasonStr": season}
        headers = {
            "accept": "text/html,application/xhtml+xml",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        result = await self._fetch_text(url, headers=headers, params=params)
        if not result:
            return []

        items: list[RankMediaItem] = []
        pattern = re.compile(
            r'<span[^>]*data-src="([^"]+)"[^>]*data-bangumiid="(\d+)"[^>]*>.*?'
            r'<a[^>]*href="/Home/Bangumi/\d+"[^>]*title="([^"]*)"',
            re.DOTALL,
        )
        for m in pattern.finditer(result):
            cover = m.group(1)
            if not cover.startswith("http"):
                cover = f"{base_url}{cover}" if cover.startswith("/") else cover
            mikan_id = m.group(2)
            title = html.unescape(m.group(3).strip())
            items.append(
                RankMediaItem(
                    title=title,
                    type_hint="tv",
                    poster=cover,
                    source_meta={"mikan_id": mikan_id, "source": "mikan"},
                    unique_seed=f"mikan:{mikan_id}",
                )
            )

        return items

    async def _resolve_detail(self, item: RankMediaItem) -> None:
        """解析单部新番详情页，获取年份和 Bangumi ID。"""
        mikan_id = item.source_meta.get("mikan_id")
        if not mikan_id:
            return

        base_url = await self._find_available_base() or "https://mikanani.me"
        url = f"{base_url}/Home/Bangumi/{mikan_id}"
        headers = {
            "accept": "text/html",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        result = await self._fetch_text(url, headers=headers)
        if not result:
            return

        bgm_m = BGM_ID_RE.search(result)
        if bgm_m:
            item.source_meta["bangumi_id"] = int(bgm_m.group(1))

        info_m = re.search(r'<p[^>]*class="bangumi-info"[^>]*>(.*?)</p>', result, re.DOTALL)
        if info_m:
            info_text = re.sub(r"<[^>]+>", "", info_m.group(1))
            for ym in YEAR_RE.finditer(info_text):
                y = int(ym.group(1))
                if 1900 <= y <= 2100:
                    item.year = str(y)
                    break

        await asyncio.sleep(DETAIL_SLEEP)

    async def _find_available_base(self) -> str | None:
        """尝试所有已知 Mikan 域名，返回第一个可用的（结果缓存，避免重复请求）。"""
        global _available_base_cache
        if _available_base_cache:
            return _available_base_cache
        async with _available_base_lock:
            if _available_base_cache:
                return _available_base_cache
            for url in MIKAN_BASE_URLS:
                try:
                    text = await self._fetch_text(url, headers={"user-agent": "Mozilla/5.0"})
                    if text and "bangumi" in text:
                        _available_base_cache = url
                        return url
                except Exception:
                    continue
        return None

    async def _fetch_text(self, url: str, headers: dict | None = None, params: dict | None = None) -> str | None:
        """用 httpx GET 请求文本内容。"""
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                return resp.text
        except Exception as e:
            logger.debug(f"[Mikan] 请求失败 {url}: {e}")
            return None
