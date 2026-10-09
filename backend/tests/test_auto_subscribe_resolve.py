"""自动订阅搜索词构建测试 — build_search_queries 变体生成逻辑。"""

from __future__ import annotations

from app.services.auto_subscribe.pipeline.resolve import build_search_queries


def test_season_title_strips_season_suffix() -> None:
    """含「第X季」的标题应剥离季节后缀，仅返回基础标题。"""
    queries = build_search_queries("鬼灭之刃 第3季")
    assert queries == ["鬼灭之刃"]


def test_season_title_with_chinese_number() -> None:
    """中文数字「第X季」也应正确处理。"""
    queries = build_search_queries("进击的巨人 第二季")
    assert queries == ["进击的巨人"]


def test_season_title_keeps_original_name_on_match() -> None:
    """含「第X季」的标题中，若基础标题只有 1 字符，应返回原列表。"""
    queries = build_search_queries("第1季")
    assert queries == ["第1季"]


def test_colon_subtitle_appends_prefix() -> None:
    """冒号副标题应追加冒号前部分，保留完整标题。"""
    queries = build_search_queries("复仇者联盟5：毁灭之日")
    assert "复仇者联盟5" in queries
    assert queries[0] == "复仇者联盟5：毁灭之日"


def test_colon_subtitle_with_fullwidth_colon() -> None:
    """全角冒号也应正确处理。"""
    queries = build_search_queries("间谍过家家: 第2部分")
    assert "间谍过家家" in queries


def test_colon_subtitle_short_prefix_not_added() -> None:
    """冒号前部分不足 2 字符的不追加。"""
    queries = build_search_queries("A：副标题")
    assert len(queries) == 1


def test_chinese_period_subtitle_appends_prefix() -> None:
    """中文句号「。」分割的副标题应追加句号前部分。"""
    queries = build_search_queries("靠死亡游戏混饭吃。 44:CLOUDY BEACH")
    assert "靠死亡游戏混饭吃" in queries
    assert queries[0] == "靠死亡游戏混饭吃。 44:CLOUDY BEACH"


def test_chinese_period_at_end_does_not_produce_variant() -> None:
    """结尾句号（分割后无内容）不应产生变体。"""
    queries = build_search_queries("靠死亡游戏混饭吃。")
    assert len(queries) == 1


def test_chapter_segment_preserves_preceding_title() -> None:
    """「第X章/篇/话」分段标识应截取分段前部分。"""
    queries = build_search_queries("剧场版 鬼灭之刃 无限城篇 第一章 猗窝座再袭")
    # 应截取到「剧场版 鬼灭之刃 无限城篇 」，而非只截到「鬼灭之刃」
    assert "剧场版 鬼灭之刃 无限城篇" in queries
    assert "鬼灭之刃 无限城篇" in queries
    assert queries[0] == "剧场版 鬼灭之刃 无限城篇 第一章 猗窝座再袭"


def test_chapter_segment_chinese_word_actions() -> None:
    """「篇」「话」「章」作为分段标识均应生效。"""
    t1 = build_search_queries("某科学的一方通行 第1话 超能力者")
    assert "某科学的一方通行" in t1

    t2 = build_search_queries("某魔法的禁书目录 第3章 必要之恶")
    assert "某魔法的禁书目录" in t2


def test_part_segment_appends_base_title() -> None:
    """「第X部分」分段标识应追加分段前的基础标题（铠真传 武士军团 第2部分 场景）。"""
    queries = build_search_queries("铠真传 武士军团 第2部分")
    assert "铠真传 武士军团" in queries
    assert queries[0] == "铠真传 武士军团 第2部分"


def test_part_segment_chinese_number() -> None:
    """中文数词的「第X部分」也应正确截取。"""
    queries = build_search_queries("某剧集 第二部分")
    assert "某剧集" in queries


def test_movie_version_prefix_stripped() -> None:
    """以「剧场版」开头的标题应追加移除前缀的变体。"""
    queries = build_search_queries("剧场版 鬼灭之刃 无限列车篇")
    assert "鬼灭之刃 无限列车篇" in queries
    assert queries[0] == "剧场版 鬼灭之刃 无限列车篇"


def test_movie_version_japanese_prefix_stripped() -> None:
    """日文「劇場版」开头也应追加移除前缀的变体。"""
    queries = build_search_queries("劇場版 呪術廻戦 0")
    assert "呪術廻戦 0" in queries


def test_movie_version_prefix_short_rest_skipped() -> None:
    """移除前缀后剩余部分不足 2 字符的，不追加。"""
    queries = build_search_queries("剧场版 a")
    assert len(queries) == 1


def test_numeric_tail_stripped() -> None:
    """数字结尾应追加剥离数字的基础名。"""
    queries = build_search_queries("高达SEED 2")
    assert "高达SEED" in queries


def test_numeric_tail_short_base_skipped() -> None:
    """剥离数字后基础名不足 2 字符的，不追加。"""
    queries = build_search_queries("A 1")
    assert len(queries) == 1


def test_original_title_always_first() -> None:
    """原始标题始终在列表首位。"""
    queries = build_search_queries("复仇者联盟4：终局之战")
    assert queries[0] == "复仇者联盟4：终局之战"


def test_dedup_variants() -> None:
    """变体应去重，不应出现重复条目。"""
    # 「辛普森一家」在冒号、句号、数字结尾、章节等多个规则下可能重复
    queries = build_search_queries("辛普森一家。第1章 辛普森一家")
    assert len(queries) == len(set(queries))


def test_empty_title() -> None:
    """空标题应仅返回自身。"""
    queries = build_search_queries("")
    assert queries == [""]


def test_plain_title_no_variants() -> None:
    """不含任何特殊模式的标题只返回自身。"""
    queries = build_search_queries("千与千寻")
    assert queries == ["千与千寻"]


# ── S2 新增变体规则（SPEC-MATCHING-RECALL §2） ────────────────


def test_space_subtitle_appends_head() -> None:
    """空格分隔的副标题应追加首段（怪兽8号 鸣海的平日 → 怪兽8号）。"""
    assert "怪兽8号" in build_search_queries("怪兽8号 鸣海的平日")
    assert "东京复仇者" in build_search_queries("东京复仇者 三天战争篇")


def test_tilde_wrapped_segment_stripped() -> None:
    """「～…～」包裹段应剥离（桃源暗鬼 ～日光・华严之泷篇～ → 桃源暗鬼）。"""
    queries = build_search_queries("桃源暗鬼 ～日光・华严之泷篇～")
    assert "桃源暗鬼" in queries
    assert queries[0] == "桃源暗鬼 ～日光・华严之泷篇～"


def test_quoted_segment_stripped() -> None:
    """「「…」」包裹段应剥离。"""
    assert "怪兽8号" in build_search_queries("怪兽8号 「鸣海的平日」")


def test_movie_prefix_head_not_added() -> None:
    """「剧场版 xxx」已由前缀规则处理，不得再产生「剧场版」这种垃圾搜索词。"""
    assert "剧场版" not in build_search_queries("剧场版 鬼灭之刃 无限城篇 第一章 猗窝座再袭")
    assert "劇場版" not in build_search_queries("劇場版 呪術廻戦 0")
