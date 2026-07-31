"""自动订阅匹配测试 — 标题归一化、相似度校验、章节后缀剥离。"""

from app.services.auto_subscribe.pipeline.matching import (
    _normalize,
    _strip_season,
    pick_best,
    title_similar_enough,
)

# ── _normalize ──────────────────────────────────────────────


def test_normalize_unifies_punctuation():
    """全角/半角标点应统一，空格应去除。"""
    assert _normalize("你好，世界！") == "你好,世界!"
    assert _normalize("（测试）") == "(测试)"
    assert _normalize("a、b、c") == "a,b,c"


def test_normalize_japanese_dot():
    """日文中点应移除，使含・标题与无标点版本精确相等。"""
    assert _normalize("城市・猎人") == "城市猎人"
    assert _normalize("ルパン三世・カリオストロの城") == "ルパン三世カリオストロの城"


def test_normalize_chinese_period():
    """中文句号应移除，使含句号标题与无标点版本精确相等。"""
    assert _normalize("你好。再见。") == "你好再见"


# ── _strip_season ───────────────────────────────────────────


def test_strip_season_removes_ji_suffix():
    """剥离'第X季'后缀。"""
    assert _strip_season("复仇者联盟 第三季") == "复仇者联盟"
    assert _strip_season("凡人修仙传第2季") == "凡人修仙传"


def test_strip_season_removes_zhang_suffix():
    """剥离'第X章'后缀。"""
    assert _strip_season("斗破苍穹第三章") == "斗破苍穹"
    assert _strip_season("斗破苍穹第3章") == "斗破苍穹"


def test_strip_season_removes_pian_suffix():
    """剥离'第X篇'后缀。"""
    assert _strip_season("鬼灭之刃第二篇") == "鬼灭之刃"
    assert _strip_season("鬼灭之刃第2篇") == "鬼灭之刃"


def test_strip_season_removes_hua_suffix():
    """剥离'第X话'后缀。"""
    assert _strip_season("海贼王第100话") == "海贼王"
    assert _strip_season("海贼王第五话") == "海贼王"


def test_strip_season_keeps_normal_title():
    """无后缀的标题应保持不变。"""
    assert _strip_season("复仇者联盟") == "复仇者联盟"
    assert _strip_season("凡人修仙传") == "凡人修仙传"


def test_strip_season_removes_colon_subtitle():
    """剥离冒号后的副标题。"""
    assert _strip_season("复仇者联盟5：毁灭之日") == "复仇者联盟5"
    assert _strip_season("复仇者联盟5: 毁灭之日") == "复仇者联盟5"


# ── pick_best ────────────────────────────────────────────────


def test_pick_best_matches_with_different_punctuation():
    """标点不同（中文句号 vs 日文中点）仍应匹配。"""
    results = [
        {"title": "城市猎人", "media_type": "tv", "vote_average": 7.0},
    ]
    matched = pick_best(results, "城市・猎人", "tv")
    assert matched is not None
    assert matched["title"] == "城市猎人"


def test_pick_best_matches_zhang_suffix_to_base():
    """搜索"第X章"后缀标题应匹配基础标题。"""
    results = [
        {"title": "凡人修仙传", "media_type": "tv", "vote_average": 7.0},
    ]
    matched = pick_best(results, "凡人修仙传第3章", "tv")
    assert matched is not None
    assert matched["title"] == "凡人修仙传"


def test_pick_best_matches_base_to_hua_suffix():
    """搜索基础标题应匹配带'第X话'后缀的标题。"""
    results = [
        {"title": "海贼王第100话", "media_type": "tv", "vote_average": 7.0},
    ]
    matched = pick_best(results, "海贼王", "tv")
    assert matched is not None
    assert matched["title"] == "海贼王第100话"


def test_pick_best_rejects_unrelated_chinese():
    """不相关的中文标题应被 title_similar_enough 拒绝（pick_best 本身会返回最高分候选）。"""
    results = [
        {"title": "海贼王", "media_type": "tv", "vote_average": 7.0},
    ]
    matched = pick_best(results, "火影忍者", "tv")
    assert matched is not None  # pick_best 降级到第5阶段返回最高分
    assert not title_similar_enough("火影忍者", matched["title"])


# ── title_similar_enough ─────────────────────────────────────


def test_title_similar_enough_different_punctuation():
    """标点不同但汉字相同应判定为相似。"""
    assert title_similar_enough("城市・猎人", "城市猎人")
    assert title_similar_enough("你好。再见。", "你好,再见!")


def test_title_similar_enough_zhang_suffix():
    """章节后缀标题与基础标题应判定为相似。"""
    assert title_similar_enough("凡人修仙传第3章", "凡人修仙传")
    assert title_similar_enough("凡人修仙传", "凡人修仙传第三章")


def test_title_similar_enough_hua_suffix():
    """话后缀标题与基础标题应判定为相似。"""
    assert title_similar_enough("海贼王第100话", "海贼王")


def test_title_similar_enough_rejects_unrelated():
    """完全不相关的中文标题应判定为不相似。"""
    assert not title_similar_enough("海贼王", "火影忍者")
    assert not title_similar_enough("斗罗大陆", "凡人修仙传")
