"""自动订阅 — 豆瓣榜单源（RSSHub RSS）。"""

from __future__ import annotations

import re
from xml.dom.minidom import parseString

import httpx

from app.core.logger import init_logger
from app.services.auto_subscribe.base import RankProvider, register
from app.services.auto_subscribe.models import RankMediaItem

logger = init_logger(__name__)

DEFAULT_RSSHUB = "https://rsshub.app"
_REQUEST_TIMEOUT = 60

_YEAR_RE = re.compile(r"(19\d\d|20\d\d)")
_DOUBAN_ID_RE = re.compile(r"/(\d+)/?$")

DOUBAN_RANKS = {
    "movie-ustop": {"path": "/douban/movie/ustop", "label": "北美票房榜", "type_hint": "movie"},
    "movie-weekly": {"path": "/douban/movie/weekly", "label": "一周口碑榜", "type_hint": "movie"},
    "movie-top250": {"path": "/douban/list/movie_top250", "label": "Top250", "type_hint": "movie"},
    "movie-hot-gaia": {"path": "/douban/movie/weekly/movie_hot_gaia", "label": "热门电影", "type_hint": "movie"},
    "tv-hot": {"path": "/douban/movie/weekly/tv_hot", "label": "热门剧集", "type_hint": "tv"},
    "tv-variety-show": {"path": "/douban/movie/weekly/show_domestic", "label": "综艺", "type_hint": "tv"},
    "movie-real-time": {
        "path": "/douban/movie/weekly/movie_real_time_hotest",
        "label": "实时热门电影",
        "type_hint": "movie",
    },
}


@register
class DoubanRankProvider(RankProvider):
    """豆瓣榜单来源：RSSHub RSS。"""

    provider_id = "douban"
    provider_name = "豆瓣榜单"

    async def fetch_async(self, options: dict) -> list[RankMediaItem]:
        """抓取豆瓣榜单。"""
        base = (options.get("douban_rsshub") or DEFAULT_RSSHUB).rstrip("/")
        rank_keys = options.get("douban_ranks") or ["movie-hot-gaia", "tv-hot"]
        custom_rss = (options.get("douban_rss_custom") or "").strip()

        urls: list[tuple[str, str | None]] = []
        for key in rank_keys:
            info = DOUBAN_RANKS.get(key)
            if info:
                urls.append((f"{base}{info['path']}", info.get("type_hint")))
        if custom_rss:
            for line in custom_rss.split("\n"):
                line = line.strip()
                if line:
                    urls.append((line if line.startswith("http") else f"{base}{line}", None))

        items: list[RankMediaItem] = []
        for url, type_hint in urls:
            try:
                items.extend(await self._fetch_rss(url, type_hint))
            except Exception as e:
                logger.warning(f"[豆瓣] RSS 抓取失败: {url[:60]}... {e}")
        return items

    async def _fetch_rss(self, url: str, type_hint: str | None = None) -> list[RankMediaItem]:
        """解析单个 RSS 源。"""
        raw = await self._fetch_text(url)
        if not raw:
            return []

        try:
            dom = parseString(raw)
        except Exception:
            return []

        items: list[RankMediaItem] = []
        for entry in dom.getElementsByTagName("item"):
            try:
                mi = self._parse_item(entry, type_hint)
                if mi:
                    items.append(mi)
            except Exception:
                continue
        return items

    def _parse_item(self, entry, source_type_hint: str | None = None) -> RankMediaItem | None:
        """从 RSS item 元素解析出 RankMediaItem。"""
        title = self._tag_text(entry, "title") or ""
        link = self._tag_text(entry, "link") or ""

        douban_id = self._parse_douban_id(link)
        description = self._tag_text(entry, "description") or ""

        year = self._parse_year(description, title)
        type_hint = source_type_hint or self._parse_type(entry)
        poster = self._parse_poster(description)

        seed = f"{title}_{year}_(DB:{douban_id})" if douban_id else title
        return RankMediaItem(
            title=title,
            year=year,
            type_hint=type_hint,
            douban_id=douban_id,
            poster=poster,
            source_meta={"douban_id": douban_id, "source": "douban"},
            unique_seed=seed,
        )

    @staticmethod
    def _tag_text(parent, tag: str) -> str:
        """获取 XML 子标签的文本内容。"""
        nodes = parent.getElementsByTagName(tag)
        if nodes and nodes[0].firstChild:
            return nodes[0].firstChild.nodeValue or ""
        return ""

    @staticmethod
    def _parse_douban_id(link: str) -> str | None:
        m = _DOUBAN_ID_RE.search(link)
        return m.group(1) if m else None

    @staticmethod
    def _parse_year(description: str, title: str) -> str | None:
        for m in _YEAR_RE.finditer(description):
            y = int(m.group(1))
            if 1900 <= y <= 2100:
                return str(y)
        for m in _YEAR_RE.finditer(title):
            y = int(m.group(1))
            if 1900 <= y <= 2100:
                return str(y)
        return None

    @staticmethod
    def _parse_type(entry) -> str | None:
        t = _tag_text_fallback(entry, "type")
        if t == "movie":
            return "movie"
        if t == "tv":
            return "tv"
        return None

    @staticmethod
    def _parse_poster(description: str) -> str | None:
        m = re.search(r'<img[^>]+src="([^"]+)"', description)
        return m.group(1) if m else None

    async def _fetch_text(self, url: str) -> str | None:
        """用 httpx GET 请求文本内容。"""
        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(url, headers={"accept": "application/xml"})
                resp.raise_for_status()
                return resp.text
        except Exception as e:
            logger.warning(f"[豆瓣] 请求失败 {url[:60]}: {e}")
            return None


def _tag_text_fallback(parent, tag: str) -> str:
    """获取 XML 子标签的文本内容（独立函数，供静态方法调用）。"""
    nodes = parent.getElementsByTagName(tag)
    if nodes and nodes[0].firstChild:
        return nodes[0].firstChild.nodeValue or ""
    return ""
