"""JEV 历史回放（Phase 4A）— 否决器变体 2：弱化年份指令的 questions 文件生成器。只读。

背景（由否决器变体 1 的结果驱动）:
    变体 1 的指令写「同名但年份…不同，视为不同作品」，否决器因此把 25 条
    「标题完全一致、只是年份口径不同」的真匹配判成不同作品（veto 概率 0.04~0.32），
    拉低了召回。而探针 C4 的注记本就指出「纯年份数值判定应留在代码里」。
    变体 2 把年份降级为弱参考，只保留「标题不完全一致 / 版本 / 季数 / 类型」的语义判定。

产出: /tmp/jev_replay/questions_veto_soft.json（与 items_veto.jsonl 配对使用）

用法:
    cd backend && .venv/bin/python scripts/jev_replay_build_veto_soft.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

OUT_DIR = Path("/tmp/jev_replay")
BASE_QUESTIONS = OUT_DIR / "questions.json"

INSTRUCTION_SOFT = (
    "『待订阅』中的条目与『搜索结果』里唯一的候选是否为同一部作品？"
    "标题完全一致且类型一致时视为同一部作品 —— 上映年/首映年的口径差异不算不同作品。"
    "标题不完全一致，或副标题、版本（电影版/剧集版、剧场版/TV版）、季数、类型不同时，视为不同作品。"
)


def main() -> int:
    """写出弱化年份指令的 questions 文件（沿用原 criteria 键）。"""
    base = json.loads(BASE_QUESTIONS.read_text(encoding="utf-8"))
    out = json.loads(json.dumps(base))
    out["same_work__0"]["instructions"] = INSTRUCTION_SOFT
    out["which__0"]["instructions"] = "哪个候选是『待订阅』指向的那部作品？没有同一部作品时选 none。"
    (OUT_DIR / "questions_veto_soft.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写出 {OUT_DIR}/questions_veto_soft.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
