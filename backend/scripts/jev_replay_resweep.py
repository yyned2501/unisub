"""JEV 阈值标定复跑 — 同一批 4A state 上重算阈值曲线（只读、零副作用）。

上游依据：`docs/SPEC-JEV-DECISION.md` §9（threshold 0.5 → 0.75 + 指令 v2 → v3）。
本脚本不调 API、不写文件，只把已固化的逐例输出按阈值重算，产出对照表。

输入（`scripts/jev_calibration/`，4A 产物固化，见同目录 README.md）:
    samples.json              712 条历史样本（A 侧决策 + truth_ids 标签 + veto_state_hash）
    items_veto_manifest.json  515 条闸门 state 的哈希序（对齐 out_*.jsonl 行序）
    out_veto_soft.jsonl       v2 指令（旧生产指令）逐例输出
    out_veto_v3.jsonl         v3 指令（现行指令）逐例输出

join 口径：samples.veto_state_hash → manifest 行序 → out jsonl 同行。
标签口径：`truth_ids`（候选标题归一化后与源标题完全相等），沿用 `scripts/jev_replay_eval.py`。

用法:
    cd backend && .venv/bin/python scripts/jev_replay_resweep.py [--dir <资产目录>]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_DIR = Path(__file__).resolve().parent / "jev_calibration"
MAIN_TAUS = (0.5, 0.75)
# spec §9.4 的 OOD 例外：逃亡者落在 [0.75, 0.80)，生产走精确匹配不进闸门
SENSITIVITY_TAU = 0.8
_SAME_WORK_KEY = "same_work__0"


@dataclass(frozen=True)
class Confusion:
    """一次阈值的混淆统计。"""

    tau: float
    tp: int
    fp: int
    fn: int
    tn: int
    missed: tuple[dict[str, Any], ...]

    @property
    def positives(self) -> int:
        """标签为「池内有同名候选」的样本数（真值非空）。"""
        return self.tp + self.fn

    @property
    def recall(self) -> float | None:
        """召回率（无正样本时 None）。"""
        return round(self.tp / self.positives, 4) if self.positives else None

    @property
    def precision(self) -> float | None:
        """精确率（无放行时 None）。"""
        return round(self.tp / (self.tp + self.fp), 4) if (self.tp + self.fp) else None

    @property
    def real_missed(self) -> tuple[dict[str, Any], ...]:
        """闸门真正会看到的漏订（A 侧已采纳、被闸门拦下）。"""
        return tuple(r for r in self.missed if r["a_accept"])


def _load_json(path: Path) -> Any:
    """读取 JSON 文件。"""
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    """读取 JSONL 文件（逐行解析）。"""
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _load_probs(directory: Path, manifest: list[str], filename: str) -> dict[str, float | None]:
    """把逐例输出的 `same_work__0.noul` 概率按 state 哈希索引。"""
    outs = _load_jsonl(directory / filename)
    if len(outs) != len(manifest):
        raise ValueError(f"{filename} 行数 {len(outs)} 与 manifest {len(manifest)} 不一致")
    return {
        state_hash: ((out.get("answers") or {}).get(_SAME_WORK_KEY) or {}).get("noul")
        for state_hash, out in zip(manifest, outs, strict=True)
    }


def join_rows(directory: Path) -> list[dict[str, Any]]:
    """join 样本与两条指令的逐例概率，返回逐条记录。"""
    manifest = _load_json(directory / "items_veto_manifest.json")
    probs_v2 = _load_probs(directory, manifest, "out_veto_soft.jsonl")
    probs_v3 = _load_probs(directory, manifest, "out_veto_v3.jsonl")
    rows: list[dict[str, Any]] = []
    for sample in _load_json(directory / "samples.json"):
        state_hash = sample.get("veto_state_hash")
        if state_hash not in probs_v2:
            continue
        rows.append({**sample, "p_v2": probs_v2[state_hash], "p_v3": probs_v3.get(state_hash)})
    return rows


def confusion(rows: list[dict[str, Any]], prob_key: str, tau: float) -> Confusion:
    """按 A 侧采纳 + 概率 ≥ tau 的口径统计混淆矩阵。"""
    tp = fp = fn = tn = 0
    missed: list[dict[str, Any]] = []
    for row in rows:
        truth = set(row["truth_ids"])
        accepted = bool(row["a_accept"]) and row[prob_key] is not None and row[prob_key] >= tau
        if accepted and row.get("a_pick_id") in truth:
            tp += 1
        elif accepted:
            fp += 1
        elif truth:
            fn += 1
            missed.append(row)
        else:
            tn += 1
    return Confusion(tau=tau, tp=tp, fp=fp, fn=fn, tn=tn, missed=tuple(missed))


def _picked(row: dict[str, Any]) -> dict[str, Any]:
    """取 A 侧选中的候选（用于打印）。"""
    return next((c for c in row["pool"] if c["id"] == row.get("a_pick_id")), {})


def _print_table(rows: list[dict[str, Any]]) -> None:
    """打印两条指令 × 两个阈值的对照表。"""
    print("\n=== 对照表：A 侧采纳 且 same_work ≥ τ（标签口径 = truth_ids）===")
    head = f"{'指令':<10} {'τ':<6} {'tp':<5} {'fp':<5} {'fn':<5} {'tn':<5} {'recall':<8} {'真实漏订':<8} {'精确率'}"
    print(head)
    for label, key in (("v2(旧)", "p_v2"), ("v3(新)", "p_v3")):
        for tau in MAIN_TAUS:
            stat = confusion(rows, key, tau)
            print(
                f"{label:<10} {tau:<6} {stat.tp:<5} {stat.fp:<5} {stat.fn:<5} {stat.tn:<5} "
                f"{str(stat.recall):<8} {len(stat.real_missed):<8} {stat.precision}"
            )


def _print_directional(rows: list[dict[str, Any]]) -> None:
    """打印 spec §9 的方向性结论核对（旧口径 vs 新口径）。"""
    old = confusion(rows, "p_v2", 0.5)
    new = confusion(rows, "p_v3", 0.75)
    print("\n=== 方向性结论（spec §9）===")
    print(f"真实漏订（A 采纳却拦下）：τ=0.5+v2 = {len(old.real_missed)} → τ=0.75+v3 = {len(new.real_missed)}")
    print(f"闸门误放行样本：τ=0.5+v2 = {old.fp} → τ=0.75+v3 = {new.fp}（标签口径误标，人工判读为同作品）")
    print(f"『同名却拦下』（真值非空且被拦，含 A 未采纳）：{len(new.missed)} 条")


def _print_details(rows: list[dict[str, Any]]) -> None:
    """打印被拦下的同名样本明细 + 0.80 敏感性（OOD 例外）。"""
    print("\n=== τ=0.75 + v3 被拦下的同名样本（含 A 未采纳，不计入闸门损失）===")
    stat = confusion(rows, "p_v3", 0.75)
    for row in sorted(stat.missed, key=lambda r: row_prob(r, "p_v3")):
        picked = _picked(row)
        print(
            f"  p_v3={row['p_v3']:.2f}  A采纳={row['a_accept']}  源:{row['source_title']}"
            f"  → 候选:{picked.get('title', '?')}  标签:{row.get('label')}  状态:{row.get('status')}"
        )

    print(f"\n=== τ={SENSITIVITY_TAU} 敏感性（spec §9.4 的 OOD 例外：逃亡者）===")
    for row in sorted(confusion(rows, "p_v3", SENSITIVITY_TAU).real_missed, key=lambda r: row_prob(r, "p_v3")):
        picked = _picked(row)
        print(
            f"  p_v3={row['p_v3']:.2f}  源:{row['source_title']}  → 候选:{picked.get('title', '?')}"
            f"  命中数:{len(row['truth_ids'])}  状态:{row.get('status')}"
        )


def row_prob(row: dict[str, Any], key: str) -> float:
    """取记录概率用于排序（None 视作 0）。"""
    return float(row[key] or 0.0)


def main() -> None:
    """入口：join 资产 → 打印对照表与结论核对。"""
    parser = argparse.ArgumentParser(description="JEV 阈值标定复跑（只读、零副作用）")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="标定资产目录（默认 scripts/jev_calibration）")
    args = parser.parse_args()

    rows = join_rows(args.dir)
    accepted = sum(1 for row in rows if row["a_accept"])
    labelled = sum(1 for row in rows if set(row["truth_ids"]))
    print(f"资产目录：{args.dir}")
    print(
        f"join 成功 {len(rows)} 条（manifest {len(_load_json(args.dir / 'items_veto_manifest.json'))} 条 state）；"
        f"A 采纳 {accepted} 条；标签真值非空 {labelled} 条"
    )
    _print_table(rows)
    _print_directional(rows)
    _print_details(rows)


if __name__ == "__main__":
    main()
