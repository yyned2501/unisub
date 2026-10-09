"""Mikan 新番解析测试 — 电影关键词识别与列表 HTML 解析。"""

from __future__ import annotations

import pytest

from app.services.auto_subscribe.mikan import BGM_ID_RE, MOVIE_KEYWORDS_RE, _extract_broadcast_year
from app.services.auto_subscribe.models import RankMediaItem

# 实测页面结构：首个 bangumi-info 块是「放送日期」，没有年份；链接为 bgm.tv
DETAIL_PAGE = """<html><body>
    <p class="bangumi-info">放送日期：星期五</p>
    <p class="bangumi-info">总集数：放送中</p>
    <p class="bangumi-info">放送开始：10/2/2026</p>
    <p class="bangumi-info">官方网站：<a href="https://example.com">官网</a></p>
    <a href="https://bgm.tv/subject/499474">Bangumi</a>
</body></html>"""


class TestMovieKeywords:
    """电影关键词正则匹配测试。"""

    @pytest.mark.parametrize(
        "title, expected",
        [
            # 剧场版相关
            ("劇場版 鬼滅の刃 無限城編", True),
            ("剧场版 魔法少女小圆", True),
            ("电影版 名侦探柯南", True),
            ("電影版 多啦A夢", True),
            # OVA / OAD
            ("Fate/stay night [OVA]", True),
            ("进击的巨人 OAD", True),
            # 特别篇 / 总集篇
            ("海贼王 特别篇", True),
            ("銀魂 特別篇 〜", True),
            ("Re:ゼロから始める異世界生活 総集編", True),
            ("无职转生 总集篇", True),
            # 普通 TV 番剧（不应匹配）
            ("葬送的芙莉莲", False),
            ("咒术回战 第2期", False),
            ("SPY×FAMILY Season 2", False),
            ("鬼灭之刃 柱训练篇", False),
            ("我推的孩子", False),
            ("2024年7月新番 第2期", False),
        ],
    )
    def test_movie_keywords_re(self, title: str, expected: bool) -> None:
        """验证电影关键词正则是否正确识别。"""
        assert bool(MOVIE_KEYWORDS_RE.search(title)) == expected

    def test_no_false_positive_on_plain_text(self) -> None:
        """纯英文字符串不应误匹配。"""
        assert not MOVIE_KEYWORDS_RE.search("Attack on Titan Season 2")
        assert not MOVIE_KEYWORDS_RE.search("Sword Art Online Alicization")


class TestFetchAnimeListTypeHint:
    """_fetch_anime_list 解析时 type_hint 推导测试。"""

    @staticmethod
    def _build_html(title: str, mikan_id: str = "12345", cover: str = "https://example.com/cover.jpg") -> str:
        """构造模拟 Mikan 新番列表 HTML。"""
        return f"""<html>
<body>
<div class="bangumi-item">
<span data-src="{cover}" data-bangumiid="{mikan_id}"></span>
<a href="/Home/Bangumi/{mikan_id}" title="{title}">{title}</a>
</div>
</body>
</html>"""

    async def _parse_one(self, title: str) -> str | None:
        """用模拟 HTML 解析单一条目，返回 type_hint。"""
        from app.services.auto_subscribe.mikan import MikanRankProvider

        provider = MikanRankProvider()
        html = self._build_html(title)

        # 模拟 _find_available_base 和 _fetch_text
        async def fake_base() -> str | None:
            return "https://mikanani.me"

        async def fake_fetch(url: str, headers: dict | None = None, params: dict | None = None) -> str | None:
            return html

        provider._find_available_base = fake_base  # type: ignore[method-assign]
        provider._fetch_text = fake_fetch  # type: ignore[method-assign]

        items = await provider._fetch_anime_list(2025, "春")
        if not items:
            return None
        return items[0].type_hint

    @pytest.mark.asyncio
    async def test_movie_keyword_sets_type_hint_movie(self) -> None:
        """标题含剧场版关键词应解析为 movie。"""
        hint = await self._parse_one("劇場版 鬼滅之刃 無限城編")
        assert hint == "movie"

    @pytest.mark.asyncio
    async def test_regular_anime_keeps_type_hint_tv(self) -> None:
        """普通新番应保持 type_hint=tv。"""
        hint = await self._parse_one("葬送的芙莉莲")
        assert hint == "tv"

    @pytest.mark.asyncio
    async def test_ova_sets_type_hint_movie(self) -> None:
        """标题含 OVA 应解析为 movie。"""
        hint = await self._parse_one("Fate/stay night [OVA]")
        assert hint == "movie"

    @pytest.mark.asyncio
    async def test_oad_sets_type_hint_movie(self) -> None:
        """标题含 OAD 应解析为 movie。"""
        hint = await self._parse_one("进击的巨人 OAD")
        assert hint == "movie"

    @pytest.mark.asyncio
    async def test_special_ep_sets_type_hint_movie(self) -> None:
        """标题含特别篇应解析为 movie。"""
        hint = await self._parse_one("海贼王 特别篇")
        assert hint == "movie"

    @pytest.mark.asyncio
    async def test_soushuuhen_sets_type_hint_movie(self) -> None:
        """标题含総集編应解析为 movie。"""
        hint = await self._parse_one("Re:ゼロから始める異世界生活 総集編")
        assert hint == "movie"

    @pytest.mark.asyncio
    async def test_multiple_items_mixed_types(self) -> None:
        """混合列表应正确区分 movie 和 tv。"""
        from app.services.auto_subscribe.mikan import MikanRankProvider

        provider = MikanRankProvider()
        html = (
            self._build_html("劇場版 鬼滅之刃 無限城編", mikan_id="1", cover="https://example.com/1.jpg")
            + self._build_html("葬送的芙莉莲", mikan_id="2", cover="https://example.com/2.jpg")
            + self._build_html("咒术回战 第2期", mikan_id="3", cover="https://example.com/3.jpg")
            + self._build_html("海贼王 特别篇", mikan_id="4", cover="https://example.com/4.jpg")
        )

        async def fake_base() -> str | None:
            return "https://mikanani.me"

        async def fake_fetch(url: str, headers: dict | None = None, params: dict | None = None) -> str | None:
            return html

        provider._find_available_base = fake_base  # type: ignore[method-assign]
        provider._fetch_text = fake_fetch  # type: ignore[method-assign]

        items = await provider._fetch_anime_list(2025, "春")
        assert len(items) == 4
        assert items[0].type_hint == "movie"
        assert items[1].type_hint == "tv"
        assert items[2].type_hint == "tv"
        assert items[3].type_hint == "movie"


class TestDetailParsing:
    """详情页解析测试 — bgm.tv 链接兼容与「放送开始」年份提取（R4）。"""

    def test_bgm_id_regex_matches_bgm_tv_link(self) -> None:
        """源侧已改用 bgm.tv 链接，正则必须兼容（旧写法让 73 部新番 bgm_id 全空）。"""
        match = BGM_ID_RE.search(DETAIL_PAGE)
        assert match is not None
        assert match.group(1) == "499474"

    def test_bgm_id_regex_keeps_legacy_bangumi_tv(self) -> None:
        """旧的 bangumi.tv 写法仍要能解析。"""
        match = BGM_ID_RE.search('<a href="https://bangumi.tv/subject/1234">x</a>')
        assert match is not None
        assert match.group(1) == "1234"

    def test_extract_year_prefers_broadcast_start_block(self) -> None:
        """首个 bangumi-info 块里没有年份，必须取「放送开始」块。"""
        assert _extract_broadcast_year(DETAIL_PAGE) == "2026"

    def test_extract_year_without_broadcast_start(self) -> None:
        """没有「放送开始」块时退回任意含年份的块；完全没有年份返回 None。"""
        assert _extract_broadcast_year('<p class="bangumi-info">官方网站：2026 年</p>') == "2026"
        assert _extract_broadcast_year('<p class="bangumi-info">放送日期：星期五</p>') is None

    @pytest.mark.asyncio
    async def test_resolve_detail_fills_bangumi_id_and_year(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_resolve_detail 应把 bgm id 与放送年份写进条目。"""
        from app.services.auto_subscribe import mikan as mikan_mod

        provider = mikan_mod.MikanRankProvider()
        item = RankMediaItem(
            title="我家的弟弟们真是让您费心了",
            type_hint="tv",
            source_meta={"mikan_id": "4095", "source": "mikan"},
            unique_seed="mikan:4095",
        )

        async def fake_base() -> str | None:
            return "https://mikanani.me"

        async def fake_fetch(url: str, headers: dict | None = None, params: dict | None = None) -> str | None:
            return DETAIL_PAGE

        async def no_sleep(_seconds: float) -> None:
            return None

        provider._find_available_base = fake_base  # type: ignore[method-assign]
        provider._fetch_text = fake_fetch  # type: ignore[method-assign]
        monkeypatch.setattr(mikan_mod.asyncio, "sleep", no_sleep)

        await provider._resolve_detail(item)  # type: ignore[attr-defined]

        assert item.source_meta["bangumi_id"] == 499474
        assert item.year == "2026"
