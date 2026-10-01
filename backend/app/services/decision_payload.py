"""JEV 采纳闸门 — state / questions 构造（纯函数，无 I/O、不读配置）。

分工（`docs/SPEC-JEV-DECISION.md`）：
    - 本模块：把 A 侧（启发式）选中的**那一个**候选翻译成 JEV 能读的 state；
    - :mod:`app.services.decision_client`：配置读取 + HTTP 调用；
    - :mod:`app.services.decision`：判定规则、降级、熔断、影子。
"""

from __future__ import annotations

from typing import Any

# 弱年份指令（Phase 4A 实测：年份严格指令会误杀 25 条真匹配，年份口径差异不算不同作品）
SAME_WORK_INSTRUCTION = (
    "『待订阅』中的条目与『搜索结果』里唯一的候选是否为同一部作品？"
    "标题完全一致且类型一致时视为同一部作品 —— 上映年/首映年的口径差异不算不同作品。"
    "标题不完全一致，或副标题、版本（电影版/剧集版、剧场版/TV版）、季数、类型不同时，视为不同作品。"
)


def build_state(
    source_title: str,
    source_year: str | int | None,
    type_hint: str,
    candidate: dict,
) -> dict[str, Any]:
    """构造 JEV state：待订阅条目 + **仅 A 侧选中的那一个**候选。

    红线：state 里只放标题/年份/类型/评分这些事实字段，禁止塞标题元信息或测试标注
    （实测：写「本条为人工注入」会把 0.93 打成 0.17）。
    """
    return {
        "待订阅": {
            "标题": source_title,
            "年份": str(source_year).strip() if source_year else "",
            "类型": type_hint if type_hint in ("movie", "tv") else "未知",
        },
        "搜索结果": [
            {
                "序号": 1,
                "标题": candidate_title(candidate),
                "年份": candidate_year(candidate),
                "类型": candidate_type(candidate),
                "评分": candidate_vote(candidate),
            }
        ],
    }


def build_questions() -> dict[str, Any]:
    """构造 questions：只问 `same_work`（扁平 key，noul 概率）。

    闸门形态下不问也不解析 `which`：单候选时它无信息量，且会引入虚假拒绝。
    """
    return {"same_work__0": {"type": "noul", "instructions": SAME_WORK_INSTRUCTION}}


# ── 候选字段提取（构造 state / 记日志用；判定规则不读这些数值） ──────────


def candidate_title(candidate: dict) -> str:
    """候选标题。"""
    return str(candidate.get("title") or candidate.get("name") or "").strip()


def candidate_type(candidate: dict) -> str:
    """候选类型（movie / tv / 未知）。"""
    raw = str(candidate.get("raw_type") or candidate.get("media_type") or "").strip().lower()
    return raw if raw in ("movie", "tv") else "未知"


def candidate_year(candidate: dict) -> int | None:
    """候选年份（无法解析时 None）。"""
    year = candidate.get("year")
    if not year:
        return None
    try:
        return int(str(year)[:4])
    except (TypeError, ValueError):
        return None


def candidate_vote(candidate: dict) -> float:
    """候选评分（缺失按 0）。"""
    try:
        return float(candidate.get("vote_average") or candidate.get("_vote_average") or 0)
    except (TypeError, ValueError):
        return 0.0
