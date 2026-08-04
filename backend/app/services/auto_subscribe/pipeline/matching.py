"""自动订阅 — 搜索结果匹配与标题相似度校验。"""

from __future__ import annotations

import re
from collections import Counter


def pick_best(results: list[dict], title: str, type_hint: str, item_year: str | None = None) -> dict | None:
    """从搜索结果中选择最佳匹配。

    匹配策略（参考 AWBotNest）:
        1. 类型过滤：type_hint 明确时优先同类型候选
        2. 精确标题匹配（忽略大小写，忽略全角/半角标点差异）
        3. 基础标题匹配：剥离季节、数字尾缀后再精确匹配
        4. 年份精确/±1 年就近匹配
        5. 子串匹配（查询词长度 >= 3 时启用）
        6. 取评分最高的
    """
    if not results:
        return None

    title_lower = title.strip().lower()

    # 按类型过滤候选
    candidates = results
    if type_hint in ("movie", "tv"):
        typed = [r for r in results if _r_type(r) == type_hint]
        candidates = typed or results

    # 归一化的查询标题
    norm_title = _normalize(title_lower)
    stripped_base = _strip_season(norm_title)

    # 阶段 1: 同类型 + 归一化精确匹配（同名候选优先按年份消歧）
    exact = [r for r in candidates if _normalize(_r_title(r)) == norm_title]
    if exact:
        return _best_by_year_then_vote(exact, item_year)

    # 阶段 2: 同类型 + 基础标题精确匹配（剥离季节/数字后缀）
    if stripped_base and stripped_base != norm_title:
        base_exact = [r for r in candidates if _normalize(_r_title(r)) == stripped_base]
        if base_exact:
            return _best_by_year_then_vote(base_exact, item_year)

    # 阶段 3: 年份就近匹配
    if type_hint in ("movie", "tv"):
        want_year = _pick_year(item_year, [_r_year(r) for r in candidates])
        if want_year is not None:
            year_exact = [r for r in candidates if _r_year(r) == want_year]
            if year_exact:
                return _best_by_vote(year_exact)
            year_near = [r for r in candidates if _r_year(r) is not None and abs(_r_year(r) - want_year) <= 1]
            if year_near:
                return _best_by_vote(year_near)

    # 阶段 4: 子串匹配（仅当查询词长度 >= 3）
    if len(title_lower) >= 3:
        substr = [r for r in candidates if title_lower in _r_title(r) or _r_title(r) in title_lower]
        if substr:
            return _best_by_vote(substr)

    # 阶段 5: 无匹配，取评分最高的
    return _best_by_vote(candidates)


def title_similar_enough(source_title: str, matched_title: str) -> bool:
    """校验搜索标题与匹配标题是否足够相似，防止完全不相关的误匹配。

    对于中文标题，要求至少 2 个共同汉字（且长度 >= 2 时匹配比例 >= 30%）；
    对于英文标题，要求单词重叠度 >= 50%。
    纯数字/过短标题（< 2 字符）跳过校验（依赖其他过滤逻辑）。
    """
    src = source_title.strip().lower()
    mtd = matched_title.strip().lower()
    if not src or not mtd:
        return False

    # 过短标题跳过（如"八仙"之类短名）
    if len(src) < 2 or len(mtd) < 2:
        return True

    # 判断是否为中文为主
    cn_chars_src = sum(1 for c in src if "一" <= c <= "鿿")
    cn_chars_mtd = sum(1 for c in mtd if "一" <= c <= "鿿")

    if cn_chars_src >= 2 or cn_chars_mtd >= 2:
        # 中文标题：取共同汉字集合
        src_set = {c for c in src if "一" <= c <= "鿿"}
        mtd_set = {c for c in mtd if "一" <= c <= "鿿"}
        if not src_set or not mtd_set:
            return False
        common = src_set & mtd_set
        # 至少 2 个共同汉字，且占较短方比例 >= 30%
        min_len = min(len(src_set), len(mtd_set))
        return len(common) >= 2 and len(common) / min_len >= 0.3
    else:
        # 英文标题：单词级重叠
        src_words = set(src.replace("-", " ").replace(":", " ").split())
        mtd_words = set(mtd.replace("-", " ").replace(":", " ").split())
        if not src_words or not mtd_words:
            return True
        common = src_words & mtd_words
        return len(common) / min(len(src_words), len(mtd_words)) >= 0.5


# ── 内部辅助函数 ──────────────────────────────────────────────


def _r_title(r: dict) -> str:
    """从搜索结果中提取标题（小写）。"""
    return (r.get("title") or r.get("name") or "").strip().lower()


def _r_type(r: dict) -> str:
    """从搜索结果中提取媒体类型。"""
    return (r.get("raw_type") or r.get("media_type") or "").lower()


def _r_year(r: dict) -> int | None:
    """从搜索结果中提取年份。"""
    y = r.get("year") or ""
    try:
        return int(str(y)[:4]) if y else None
    except (ValueError, TypeError):
        return None


def _normalize(s: str) -> str:
    """归一化：全角/半角标点统一、日文中点转换、多余空格去除。"""
    s = s.replace("，", ",").replace("？", "?").replace("！", "!").replace("。", "")
    s = s.replace("（", "(").replace("）", ")").replace("、", ",").replace(" ", "")
    s = s.replace("・", "")  # 日文中点 → 移除，使含・标题与无标点版本精确相等
    return s


def _strip_season(s: str) -> str:
    """剥离季节后缀、章节后缀（章/篇/话/部分）、副标题和末尾数字。"""
    s = re.sub(r"第[一二三四五六七八九十百\d]+(?:季|章|篇|话|部分)", "", s).strip()
    s = re.sub(r"[\s\-_]*\d{1,4}$", "", s).strip()
    # 剥离冒号副标题："复仇者联盟5：毁灭之日" → "复仇者联盟5"
    s = re.split(r"[：:]\s*", s, maxsplit=1)[0].strip()
    return s


def _pick_year(item_year: str | None, result_years: list[int | None]) -> int | None:
    """从候选结果年份中选取最合理的匹配年份。"""
    if item_year:
        try:
            return int(str(item_year)[:4])
        except (ValueError, TypeError):
            pass
    # 取出现最多的年份
    valid = [y for y in result_years if y is not None]
    if not valid:
        return None
    return Counter(valid).most_common(1)[0][0]


def _best_by_year_then_vote(results: list[dict], item_year: str | None) -> dict:
    """优先按源年份匹配，再以评分选择同年候选。"""
    if item_year:
        try:
            want_year = int(str(item_year)[:4])
            exact = [r for r in results if str(r.get("year") or "")[:4] == str(want_year)]
            if exact:
                return _best_by_vote(exact)
            near = [
                r
                for r in results
                if str(r.get("year") or "")[:4].isdigit() and abs(int(str(r.get("year"))[:4]) - want_year) <= 1
            ]
            if near:
                return _best_by_vote(near)
        except (ValueError, TypeError):
            pass
    return _best_by_vote(results)


def _best_by_vote(results: list[dict]) -> dict:
    """从结果列表中取评分最高的。"""
    best = results[0]
    best_vote = float(best.get("vote_average") or best.get("_vote_average") or 0)
    for r in results[1:]:
        vote = float(r.get("vote_average") or r.get("_vote_average") or 0)
        if vote > best_vote:
            best_vote = vote
            best = r
    return best
