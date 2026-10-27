"""JEV 历史回放（Phase 4A）— 评价脚本：A/B 混淆矩阵 + 阈值扫描 + 成本延迟。只读。

输入:
    /tmp/jev_replay/samples.json         （jev_replay_build.py 产出，含 A 侧决策与标签）
    /tmp/jev_replay/items_manifest.json  （行顺序 → state 哈希，用于校验 out.jsonl 行序）
    /tmp/jev_replay/out.jsonl            （jev.py map 产出，含 answers/usage/elapsed_s）
输出:
    /tmp/jev_replay/metrics.json + 控制台表格（供报告引用）

用法:
    cd backend && .venv/bin/python scripts/jev_replay_eval.py
"""

from __future__ import annotations

import hashlib
import json
import statistics
import sys
from pathlib import Path

OUT_DIR = Path("/tmp/jev_replay")
# typesafe 输入单价（USD / 1M tokens）：$0.042/M 输入；输出按 0 计（JEV 只出结构化小响应）
PRICE_INPUT_PER_M = 0.042
# jev.py map 在输入行上追加的字段（重建 state 时需剔除）
_ADDED_KEYS = {"answers", "usage", "model_version", "elapsed_s", "_error"}


def _accept_b(prob: float | None, choice: str | None, threshold: float) -> bool:
    """B 侧判定：same_work 概率 ≥ 阈值 且 which != none → 采纳。"""
    if prob is None:
        return False
    return prob >= threshold and str(choice) not in ("", "none", "None")


def _which_index(choice: str | None, pool_size: int) -> int | None:
    """choice 键（cand_N）→ 候选下标（0 起）；none / 越界 → None。"""
    if not choice or not str(choice).startswith("cand_"):
        return None
    try:
        idx = int(str(choice).split("_", 1)[1]) - 1
    except ValueError:
        return None
    return idx if 0 <= idx < pool_size else None


def _row_pick(kind: str, row: dict, threshold: float) -> tuple[bool, int | None]:
    """按侧别取出（是否采纳, 采纳的候选 id）。

    A      = 现有启发式（pick_best + title_similar_enough）
    B      = JEV 主决策器（候选全量入 state）
    A+V    = A 采纳后再由 JEV 否决器复核（JEV 只判 A 选中的那一个候选）
    """
    if kind == "A":
        return bool(row["a_accept"]), row.get("a_pick_id")
    if kind in ("A+V", "A+V2"):
        accept, picked = _row_pick("A", row, threshold)
        if not accept:
            return False, None
        tag = "v" if kind == "A+V" else "v2"
        veto_ok = _accept_b(row.get(f"{tag}_prob"), row.get(f"{tag}_choice"), threshold)
        return veto_ok, (picked if veto_ok else None)
    if kind == "A+V2s":
        # 单候选否决形态：A 已经选定了候选，「which 选哪个」无意义
        # （实测有 21 例 same_work ≥0.7 却 which=none 的自相矛盾答案），只看同作品概率
        accept, picked = _row_pick("A", row, threshold)
        prob = row.get("v2_prob")
        veto_ok = accept and prob is not None and prob >= threshold
        return bool(veto_ok), (picked if veto_ok else None)
    accept = _accept_b(row.get("b_prob"), row.get("b_choice"), threshold)
    idx = _which_index(row.get("b_choice"), len(row["pool"]))
    return accept, (row["pool"][idx]["id"] if idx is not None else None)


def _confusion(rows: list[dict], kind: str, threshold: float, *, strict_year: bool = False) -> dict:
    """混淆矩阵。「正确采纳」= 采纳了真值集合内的候选。

    真值缺失（候选池里没有同一部作品）时，采纳任何候选都记为 FP（误订）。
    """
    tp = fp = fn = tn = 0
    for r in rows:
        truth = set(r["truth_ids_yearstrict" if strict_year else "truth_ids"])
        accept, picked = _row_pick(kind, r, threshold)
        if accept and picked in truth:
            tp += 1
        elif accept:
            fp += 1
        elif truth:
            fn += 1
        else:
            tn += 1
    total = len(rows)
    pos = sum(1 for r in rows if set(r["truth_ids_yearstrict" if strict_year else "truth_ids"]))
    neg = total - pos
    return {
        "kind": kind,
        "strict_year": strict_year,
        "threshold": threshold,
        "total": total,
        "positives": pos,
        "negatives": neg,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "accuracy": round((tp + tn) / total, 4) if total else None,
        "precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "fp_rate": round(fp / total, 4) if total else None,
        "fp_rate_on_neg": round(fp / neg, 4) if neg else None,
        "recall": round(tp / pos, 4) if pos else None,
    }


def _load_rows(samples: list[dict]) -> tuple[list[dict], dict]:
    """把 out.jsonl 的答案按 state 哈希贴回样本，并校验行序。"""
    manifest = json.loads((OUT_DIR / "items_manifest.json").read_text(encoding="utf-8"))
    out_rows = [
        json.loads(line) for line in (OUT_DIR / "out.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    by_hash: dict[str, dict] = {}
    mismatch = 0
    for i, rec in enumerate(out_rows):
        state = {k: v for k, v in rec.items() if k not in _ADDED_KEYS}
        digest = hashlib.sha1(json.dumps(state, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if i < len(manifest) and manifest[i] != digest:
            mismatch += 1
        by_hash.setdefault(digest, rec)
    diag = {
        "manifest_rows": len(manifest),
        "out_rows": len(out_rows),
        "hash_mismatch": mismatch,
        "missing_states": sum(1 for h in manifest if h not in by_hash),
    }
    rows: list[dict] = []
    for s in samples:
        rec = by_hash.get(s["state_hash"])
        merged = dict(s)
        merged["b_has_response"] = bool(rec and "answers" in rec)
        if rec:
            ans = rec.get("answers") or {}
            merged["b_prob"] = (ans.get("same_work__0") or {}).get("noul")
            merged["b_choice"] = (ans.get("which__0") or {}).get("choice")
            merged["b_confidence"] = (ans.get("which__0") or {}).get("confidence")
            merged["elapsed_s"] = rec.get("elapsed_s")
            merged["usage"] = rec.get("usage") or {}
            merged["model_version"] = rec.get("model_version")
            merged["b_error"] = rec.get("_error")
        rows.append(merged)
    return rows, diag


def _load_veto_rows(
    samples: list[dict], *, stem: str = "items_veto", out_name: str = "out_veto.jsonl", prefix: str = "v"
) -> dict:
    """把否决器批次的答案按哈希贴回样本（prefix 区分不同指令变体）。"""
    veto_items = OUT_DIR / f"{stem}.jsonl"
    veto_out = OUT_DIR / out_name
    if not (veto_items.exists() and veto_out.exists()):
        return {}
    manifest = json.loads((OUT_DIR / f"{stem}_manifest.json").read_text(encoding="utf-8"))
    out_rows = [json.loads(line) for line in veto_out.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_hash: dict[str, dict] = {}
    for i, rec in enumerate(out_rows):
        state = {k: v for k, v in rec.items() if k not in _ADDED_KEYS}
        digest = hashlib.sha1(json.dumps(state, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if i < len(manifest) and manifest[i] != digest:
            continue
        by_hash.setdefault(digest, rec)
    out: dict[str, dict] = {}
    for s in samples:
        vh = s.get("veto_state_hash")
        rec = by_hash.get(vh) if vh else None
        if rec is None:
            continue
        ans = rec.get("answers") or {}
        out[s["state_hash"]] = {
            f"{prefix}_prob": (ans.get("same_work__0") or {}).get("noul"),
            f"{prefix}_choice": (ans.get("which__0") or {}).get("choice"),
            f"{prefix}_elapsed_s": rec.get("elapsed_s"),
            f"{prefix}_usage": rec.get("usage") or {},
        }
    return out


def _subgroups(rows: list[dict], threshold: float) -> dict:
    """关键子群：高置信负样本 / 同名多候选（年份缺失） / 年份严格口径。"""
    hard_neg = [r for r in rows if r["no_same_title"]]
    amb = [r for r in rows if r["year_ambiguous"]]
    year_known = [r for r in rows if r["source_year"]]
    return {
        "hard_negative": {
            "n": len(hard_neg),
            "A": _confusion(hard_neg, "A", threshold),
            "B": _confusion(hard_neg, "B", threshold),
            "A+V": _confusion(hard_neg, "A+V", threshold),
            "A+V2": _confusion(hard_neg, "A+V2", threshold),
            "A+V2s": _confusion(hard_neg, "A+V2s", threshold),
        },
        "year_ambiguous": {
            "n": len(amb),
            "A": _confusion(amb, "A", threshold),
            "B": _confusion(amb, "B", threshold),
            "A+V": _confusion(amb, "A+V", threshold),
            "A+V2": _confusion(amb, "A+V2", threshold),
            "A+V2s": _confusion(amb, "A+V2s", threshold),
        },
        "year_known_yearstrict": {
            "n": len(year_known),
            "A": _confusion(year_known, "A", threshold, strict_year=True),
            "B": _confusion(year_known, "B", threshold, strict_year=True),
            "A+V": _confusion(year_known, "A+V", threshold, strict_year=True),
            "A+V2": _confusion(year_known, "A+V2", threshold, strict_year=True),
            "A+V2s": _confusion(year_known, "A+V2s", threshold, strict_year=True),
        },
    }


def main() -> int:
    """计算 A/B 指标、阈值扫描、子群与成本延迟，落盘 metrics.json。"""
    samples = json.loads((OUT_DIR / "samples.json").read_text(encoding="utf-8"))
    rows, diag = _load_rows(samples)
    veto = _load_veto_rows(samples)
    veto2 = _load_veto_rows(samples, out_name="out_veto_soft.jsonl", prefix="v2")
    for r in rows:
        v = veto.get(r["state_hash"])
        v2 = veto2.get(r["state_hash"])
        if v:
            r.update(v)
        if v2:
            r.update(v2)
        r["v_has_response"] = bool(v)
        r["v2_has_response"] = bool(v2)
    answered = [r for r in rows if r["b_has_response"] and r.get("b_prob") is not None]
    errors = [r for r in rows if r.get("b_error")]

    scan = []
    for t in [round(0.1 * i, 2) for i in range(1, 10)]:
        scan.append(
            {
                "threshold": t,
                "A": _confusion(rows, "A", t),
                "B": _confusion(rows, "B", t),
                "A+V": _confusion(rows, "A+V", t),
                "A+V2": _confusion(rows, "A+V2", t),
                "A+V2s": _confusion(rows, "A+V2s", t),
            }
        )
    a_recall = scan[0]["A"]["recall"] or 0
    best = max(scan, key=lambda s: (s["B"]["accuracy"] or 0, s["B"]["recall"] or 0))
    # 否决器推荐阈值：召回不低于 A 侧 5pp，取误订率最低
    veto_valid = [s for s in scan if (s["A+V"]["recall"] or 0) >= a_recall - 0.05]
    veto_best = max(veto_valid or scan, key=lambda s: (-(s["A+V"]["fp_rate"] or 1), s["A+V"]["recall"] or 0))
    veto2_valid = [s for s in scan if (s["A+V2"]["recall"] or 0) >= a_recall - 0.05]
    veto2_best = max(veto2_valid or scan, key=lambda s: (-(s["A+V2"]["fp_rate"] or 1), s["A+V2"]["recall"] or 0))
    veto2s_valid = [s for s in scan if (s["A+V2s"]["recall"] or 0) >= a_recall - 0.05]
    veto2s_best = max(veto2s_valid or scan, key=lambda s: (-(s["A+V2s"]["fp_rate"] or 1), s["A+V2s"]["recall"] or 0))
    # 细粒度扫描：决策门槛落在 0.4~0.6，用 0.025 步长确认通过区间
    scan_fine = []
    for i in range(14, 27):
        t = round(0.025 * i, 3)
        scan_fine.append(
            {
                "threshold": t,
                "A+V": _confusion(rows, "A+V", t),
                "A+V2": _confusion(rows, "A+V2", t),
                "A+V2s": _confusion(rows, "A+V2s", t),
            }
        )

    lat = sorted(r["elapsed_s"] for r in answered if r.get("elapsed_s") is not None)
    p95 = lat[min(len(lat) - 1, int(round(0.95 * (len(lat) - 1))))] if lat else None
    tokens_in = sum((r["usage"].get("input_tokens") or r["usage"].get("prompt_tokens") or 0) for r in answered)
    tokens_known = any((r["usage"].get("input_tokens") or r["usage"].get("prompt_tokens")) for r in answered)
    cost = tokens_in / 1_000_000 * PRICE_INPUT_PER_M

    accepted_b = [r for r in answered if _accept_b(r.get("b_prob"), r.get("b_choice"), best["threshold"])]
    vaccepted = [r for r in rows if r["v_has_response"] and _row_pick("A+V", r, veto_best["threshold"])[0]]
    v_lat = sorted(r["v_elapsed_s"] for r in rows if r.get("v_elapsed_s") is not None)
    v_tokens = sum((r.get("v_usage") or {}).get("input_tokens", 0) for r in rows if r.get("v_usage"))
    vr = [r for r in rows if r["v_has_response"]]
    v_fp = sum(1 for r in vr if r["a_accept"] and r.get("v_prob") is not None and r["v_prob"] < veto_best["threshold"])
    summary = {
        "samples": len(rows),
        "unique_states": diag["manifest_rows"],
        "answered_samples": len(answered),
        "errors": len(errors),
        "error_sample": errors[0].get("b_error") if errors else None,
        "join": diag,
        "model_versions": sorted({r.get("model_version") for r in answered if r.get("model_version")}),
        "usage_keys_sample": answered[0]["usage"] if answered else None,
        "tokens_input_total": tokens_in if tokens_known else None,
        "cost_usd_total": round(cost, 6) if tokens_known else None,
        "cost_usd_per_call": round(cost / len(answered), 6) if (tokens_known and answered) else None,
        "latency_avg_s": round(statistics.fmean(lat), 3) if lat else None,
        "latency_p50_s": round(statistics.median(lat), 3) if lat else None,
        "latency_p95_s": round(p95, 3) if p95 is not None else None,
        "veto_answered": len(vr),
        "veto_tokens_input_total": v_tokens or None,
        "veto_cost_usd_total": round(v_tokens / 1_000_000 * PRICE_INPUT_PER_M, 6) if v_tokens else None,
        "veto_cost_usd_per_call": round(v_tokens / 1_000_000 * PRICE_INPUT_PER_M / len(vr), 6)
        if (v_tokens and vr)
        else None,
        "veto_latency_avg_s": round(statistics.fmean(v_lat), 3) if v_lat else None,
        "veto_latency_p95_s": round(v_lat[min(len(v_lat) - 1, int(round(0.95 * (len(v_lat) - 1))))], 3)
        if v_lat
        else None,
        "veto_vetoed_a_accepts": v_fp,
        "a_overall": _confusion(rows, "A", 0.7),
        "b_overall_0_7": _confusion(rows, "B", 0.7),
        "av_overall_0_7": _confusion(rows, "A+V", 0.7),
        "av_overall_veto_best": _confusion(rows, "A+V", veto_best["threshold"]),
        "av2_overall_0_7": _confusion(rows, "A+V2", 0.7),
        "av2_overall_veto2_best": _confusion(rows, "A+V2", veto2_best["threshold"]),
        "av2s_overall_0_7": _confusion(rows, "A+V2s", 0.7),
        "av2s_overall_best": _confusion(rows, "A+V2s", veto2s_best["threshold"]),
        "a_matched_history": sum(1 for r in rows if r["a_matched_history"]),
        "a_accept_but_history_differs": sum(
            1 for r in rows if r["a_accept"] and r["hist_tmdb_id"] and r["a_pick_id"] != r["hist_tmdb_id"]
        ),
        "b_accept_but_history_differs": sum(
            1 for r in accepted_b if r["hist_tmdb_id"] and _row_pick("B", r, best["threshold"])[1] != r["hist_tmdb_id"]
        ),
        "av_accept_but_history_differs": sum(
            1
            for r in vaccepted
            if r["hist_tmdb_id"] and _row_pick("A+V", r, veto_best["threshold"])[1] != r["hist_tmdb_id"]
        ),
        "subgroups_0_7": _subgroups(rows, 0.7),
        "subgroups_veto_best": _subgroups(rows, veto_best["threshold"]),
        "scan": scan,
        "scan_fine": scan_fine,
        "best_threshold": best["threshold"],
        "veto_best_threshold": veto_best["threshold"],
        "veto2_best_threshold": veto2_best["threshold"],
        "veto2s_best_threshold": veto2s_best["threshold"],
        "veto2_answered": sum(1 for r in rows if r["v2_has_response"]),
    }
    (OUT_DIR / "metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"样本 {summary['samples']}（去重 state {summary['unique_states']}）；有响应 {summary['answered_samples']}；失败 {summary['errors']}"
    )
    print(f"行序校验: {json.dumps(diag, ensure_ascii=False)}")
    print(f"模型版本 {summary['model_versions']}；usage 样例 {summary['usage_keys_sample']}")
    print(
        f"主决策器延迟 avg/p50/p95 = {summary['latency_avg_s']}/{summary['latency_p50_s']}/{summary['latency_p95_s']} s"
    )
    print(
        f"token 合计 {summary['tokens_input_total']}；总成本 ${summary['cost_usd_total']}；单次 ${summary['cost_usd_per_call']}"
    )
    print(
        f"否决器: {summary['veto_answered']} 次；单次 ${summary['veto_cost_usd_per_call']}；p95 {summary['veto_latency_p95_s']}s；被否决 {summary['veto_vetoed_a_accepts']} 次"
    )
    print(f"A 与历史一致 {summary['a_matched_history']}/{summary['samples']}")
    print()
    print(
        "阈值 | A: acc/fp/recall | B: acc/fp/recall | A+V: acc/fp/recall | A+V2: acc/fp/recall | A+V2s: acc/fp/recall"
    )
    for s in scan:
        a, b, v, v2, v2s = s["A"], s["B"], s["A+V"], s["A+V2"], s["A+V2s"]
        print(
            f"{s['threshold']:.2f} | A {a['accuracy']} {a['fp_rate']} {a['recall']} "
            f"| B {b['accuracy']} {b['fp_rate']} {b['recall']} "
            f"| A+V {v['accuracy']} {v['fp_rate']} {v['recall']} "
            f"| A+V2 {v2['accuracy']} {v2['fp_rate']} {v2['recall']} "
            f"| A+V2s {v2s['accuracy']} {v2s['fp_rate']} {v2s['recall']}"
        )
    print()
    print("A 总体:", json.dumps(summary["a_overall"], ensure_ascii=False))
    print("B 总体(0.7):", json.dumps(summary["b_overall_0_7"], ensure_ascii=False))
    print("A+V 总体(0.7):", json.dumps(summary["av_overall_0_7"], ensure_ascii=False))
    print("A+V2 总体(0.7):", json.dumps(summary["av2_overall_0_7"], ensure_ascii=False))
    print("A+V 总体(否决器推荐阈值):", json.dumps(summary["av_overall_veto_best"], ensure_ascii=False))
    print("A+V2 总体(弱年份否决器推荐阈值):", json.dumps(summary["av2_overall_veto2_best"], ensure_ascii=False))
    print("A+V2s 总体(0.7):", json.dumps(summary["av2s_overall_0_7"], ensure_ascii=False))
    print("子群(0.7):", json.dumps(summary["subgroups_0_7"], ensure_ascii=False))
    print("主决策器最优准确率阈值:", summary["best_threshold"])
    print("否决器推荐阈值（召回不低于 A，取误订率最低）:", summary["veto_best_threshold"])
    print("弱年份否决器推荐阈值:", summary["veto2_best_threshold"])
    print("子群(否决器推荐阈值):", json.dumps(summary["subgroups_veto_best"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
