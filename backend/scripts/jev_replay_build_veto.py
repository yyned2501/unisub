"""JEV 历史回放（Phase 4A）— 否决器变体：把 A 侧已采纳的那个候选单独交给 JEV 复核。只读。

动机（由回放实验 1 的结果驱动）: A 侧 20 个误订全部是「候选池里根本没有同一部作品却采纳了模糊候选」
（``matching.py:64`` 的 ``_best_by_vote`` 兜底）。因此除了「JEV 当主决策器」（候选全量入 state），
还要测「JEV 当否决器」：只把 A 已采纳的那一个候选交给 JEV 判定是否同一部作品 —— 这与
``scripts/jev_ab_probe.py`` 的探针形态一致，也最省 token。

输入:  /tmp/jev_replay/samples.json（含 A 侧决策与候选池）
产出:  /tmp/jev_replay/items_veto.jsonl + items_veto_manifest.json（配同一份 questions.json）

用法:
    cd backend && .venv/bin/python scripts/jev_replay_build_veto.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

OUT_DIR = Path("/tmp/jev_replay")


def _veto_state(sample: dict) -> dict | None:
    """构造否决器 state：搜索结果只保留 A 侧采纳的那一个候选。"""
    if sample.get("a_pick_id") is None:
        return None
    picked = next((c for c in sample["pool"] if c["id"] == sample["a_pick_id"]), None)
    if picked is None:
        return None
    return {
        "待订阅": {
            "标题": sample["source_title"],
            "年份": sample["source_year"],
            "类型": sample["type_hint"] if sample["type_hint"] in ("movie", "tv") else "未知",
        },
        "搜索结果": [
            {"序号": 1, "标题": picked["title"], "年份": picked["year"], "类型": picked["type"], "评分": picked["vote"]}
        ],
    }


def main() -> int:
    """按样本写出否决器输入（去重 + 行序清单）。"""
    samples = json.loads((OUT_DIR / "samples.json").read_text(encoding="utf-8"))
    uniq: dict[str, dict] = {}
    manifest: list[str] = []
    for s in samples:
        state = _veto_state(s)
        if state is None:
            continue
        digest = hashlib.sha1(json.dumps(state, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        s["veto_state_hash"] = digest
        if digest not in uniq:
            uniq[digest] = state
            manifest.append(digest)
    (OUT_DIR / "samples.json").write_text(json.dumps(samples, ensure_ascii=False), encoding="utf-8")
    with (OUT_DIR / "items_veto.jsonl").open("w", encoding="utf-8") as f:
        for digest in manifest:
            f.write(json.dumps(uniq[digest], ensure_ascii=False) + "\n")
    (OUT_DIR / "items_veto_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"否决器样本 {len(manifest)} 行（样本 {len(samples)}）→ items_veto.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
