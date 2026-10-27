"""UniSub 匹配链路 A/B 对照：现有启发式 vs JEV 判定。

目的：拿到「JEV 是否值得引入」的真实数据，而不是靠感觉。
- A 侧：直接 import 项目里的 app/services/auto_subscribe/pipeline/matching.py
- B 侧：调用 TypeSafe JEV（noul 概率 + choice 选择）

用法: cd backend && set -a && source .env && set +a && .venv/bin/python scripts/jev_ab_probe.py
"""

import json
import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # backend/
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))        # jev.py（四 profile 共享）

from app.services.auto_subscribe.pipeline.matching import pick_best, title_similar_enough  # noqa: E402
from jev import system_one  # noqa: E402

# 案例：source = 待订阅条目；candidates = 搜索实际会返回的候选
# want=True 表示"应当采纳候选"，False 表示"应当拒绝"
CASES = [
    {
        "id": "C1-字面重叠陷阱",
        "source": {"title": "海上心狱", "year": "2026", "type": "movie"},
        "candidates": [{"title": "海上钢琴师", "year": 1998, "media_type": "movie", "vote_average": 8.7}],
        "want": False,
        "note": "共同汉字『海上』=2 且占较短方 50% → 现有阈值判为足够相似",
    },
    {
        "id": "C2-同名不同年",
        "source": {"title": "实习生", "year": "2026", "type": "movie"},
        "candidates": [{"title": "实习生", "year": 2015, "media_type": "movie", "vote_average": 7.2}],
        "want": False,
        "note": "标题完全相同、年份差 11 年；现有逻辑走 _best_by_vote 兜底",
    },
    {
        "id": "C3-同IP不同条目",
        "source": {"title": "百分之十：电影版", "year": "2026", "type": "movie"},
        "candidates": [{"title": "百分之十", "year": 2015, "media_type": "tv", "vote_average": 7.8}],
        "want": False,
        "note": "剥离冒号副标题后精确命中剧版；类型不符但回退到未过滤结果",
    },
    {
        "id": "C4-同名差2年(数值边界)",
        "source": {"title": "蓦然回首", "year": "2026", "type": "movie"},
        "candidates": [{"title": "蓦然回首", "year": 2024, "media_type": "movie", "vote_average": 8.4}],
        "want": False,
        "note": "纯年份数值判定 —— 预期 JEV 不占优，年份比较应留在代码里",
    },
    {
        "id": "C5-正例(完全一致)",
        "source": {"title": "一瓯春", "year": "2026", "type": "tv"},
        "candidates": [{"title": "一瓯春", "year": 2026, "media_type": "tv", "vote_average": 0.0}],
        "want": True,
        "note": "真实订阅项，标题+年份+类型全中",
    },
    {
        "id": "C6-正例(真实订阅项)",
        "source": {"title": "核战边缘", "year": "2026", "type": "movie"},
        "candidates": [{"title": "核战边缘", "year": 2026, "media_type": "movie", "vote_average": 6.1}],
        "want": True,
        "note": "真实订阅项",
    },
]

QUESTIONS = {
    "same_work": {
        "type": "noul",
        "instructions": (
            "『待订阅』中的条目与『搜索结果』里是否存在同一部作品？"
            "同名但年份、类型或版本（电影版/剧集版、剧场版/TV版、同一IP的不同季）不同，视为不同作品。"
            "搜索结果里没有同一部作品时，答案为不成立。"
        ),
    },
    "which": {
        "type": "choice",
        "instructions": "哪个候选是『待订阅』指向的那部作品？没有同一部作品时选 none。",
    },
}


def ask_jev(case: dict) -> dict:
    """对单个案例问 JEV：是否同一作品（noul）+ 从候选中选一个（choice）。"""
    labels = {f"cand_{i+1}": f"候选{i+1}: {c['title']}（{c.get('year')}，{c.get('media_type')}）"
              for i, c in enumerate(case["candidates"])}
    labels["none"] = "以上都不是同一部作品"
    questions = {
        "same_work__0": dict(QUESTIONS["same_work"]),
        "which__0": dict(QUESTIONS["which"], criteria=labels),
    }
    state = {
        "待订阅": {"标题": case["source"]["title"], "年份": case["source"]["year"], "类型": case["source"]["type"]},
        "搜索结果": [
            {"序号": i + 1, "标题": c["title"], "年份": c.get("year"), "类型": c.get("media_type"), "评分": c.get("vote_average")}
            for i, c in enumerate(case["candidates"])
        ],
    }
    resp, elapsed = system_one(state, questions, model="jev-latest")
    return {"resp": resp, "elapsed": elapsed}


def main() -> int:
    rows = []
    for case in CASES:
        src = case["source"]
        cand = case["candidates"][0]
        # A 侧：现有实现
        a_similar = title_similar_enough(src["title"], cand["title"])
        a_pick = pick_best(case["candidates"], src["title"], src["type"], src["year"])
        a_accept = bool(a_pick) and a_similar

        # B 侧：JEV
        out = ask_jev(case)
        resp = out["resp"]
        ans = resp.get("answers", {})
        sw = ans.get("same_work__0", {}) or {}
        wh = ans.get("which__0", {}) or {}
        b_prob = sw.get("noul")
        b_choice = wh.get("choice")
        b_accept = (b_prob is not None and b_prob >= 0.7) and b_choice not in (None, "none")

        row = {
            "id": case["id"],
            "want": case["want"],
            "A_相似": a_similar,
            "A_采纳": a_accept,
            "A_选中": (a_pick or {}).get("title"),
            "B_同一作品概率": b_prob,
            "B_选择": b_choice,
            "B_置信": wh.get("confidence"),
            "B_采纳": b_accept,
            "耗时s": round(out["elapsed"], 3),
            "note": case["note"],
        }
        rows.append(row)
        print(f"[{case['id']}] want={case['want']} | A(相似={a_similar} 采纳={a_accept} 选中={row['A_选中']}) "
              f"| B(p={b_prob} 选={b_choice} 采纳={b_accept})", flush=True)

    print("\n=== 首例原始响应（确认字段形状）===")
    print(json.dumps(rows[0]["id"], ensure_ascii=False), "→", json.dumps(rows[1], ensure_ascii=False, indent=2))
    print("\n=== 汇总 ===")
    a_wrong = [r["id"] for r in rows if r["A_采纳"] != r["want"]]
    b_wrong = [r["id"] for r in rows if r["B_采纳"] != r["want"]]
    print(f"A(现有启发式) 错判: {a_wrong}")
    print(f"B(JEV)        错判: {b_wrong}")
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
