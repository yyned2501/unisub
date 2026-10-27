"""JEV 历史回放（Phase 4A）— 样本导出 + 候选集重建 + A 侧启发式决策。**只读**。

数据来源（均只读）:
    1. ``app/data/auto_subscribe_history.json`` → ``handled``：真实榜单条目（源标题 + 历史匹配 tmdb_id + 状态）
    2. ``activity_logs``（PostgreSQL）→ ``unsubscribe`` 记录，用于弱负标签
    3. TMDB / NextFind 搜索接口 → 重建候选集（与生产同一条搜索链路，关闭 AI 辅助）

产出（默认 ``/tmp/jev_replay/``）:
    samples.json     每样本元信息 + 候选池 + A 侧决策 + 标签
    items.jsonl      给 ``~/.hermes/scripts/jev.py map`` 的输入（id + state，state 只含真实字段）
    questions.json   同一组问题（same_work: noul / which: choice）

红线: 不写生产库、不改 ``pipeline/`` 代码、不落任何密钥。

用法:
    cd backend && set -a && source .env && set +a
    .venv/bin/python scripts/jev_replay_build.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/

from sqlalchemy import text  # noqa: E402

from app.core.database import async_session  # noqa: E402
from app.services import get_nf_service, get_tmdb_service  # noqa: E402
from app.services.auto_subscribe.pipeline.matching import (  # noqa: E402
    _normalize,
    pick_best,
    title_similar_enough,
)
from app.services.auto_subscribe.pipeline.resolve import (  # noqa: E402
    _search_with_variants,
    build_search_queries,
)

OUT_DIR = Path("/tmp/jev_replay")
HISTORY_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "auto_subscribe_history.json"
CACHE_PATH = OUT_DIR / "search_cache.json"
_MAX_CONCURRENCY = 5
# 源年份与候选年份容差：跨年上映（12 月片次年入库）视为同一部作品
_YEAR_TOLERANCE = 1


def _seed_year(seed: str) -> str | None:
    """从 douban 历史键 ``标题_2026_(DB:123)`` 解析源年份；其他来源无年份。"""
    m = re.search(r"_(\d{4})_\(DB:\d+\)$", seed)
    return m.group(1) if m else None


def _base_title(seed: str) -> str:
    """历史键 → 榜单原始标题（douban 键去掉 ``_年份_(DB:id)`` 后缀）。"""
    return re.sub(r"_\d{4}_\(DB:\d+\)$", "", seed)


def _cand_title(c: dict) -> str:
    """候选标题（与 matching._r_title 同口径）。"""
    return (c.get("title") or c.get("name") or "").strip()


def _cand_type(c: dict) -> str:
    """候选媒体类型。"""
    return str(c.get("raw_type") or c.get("media_type") or "").lower()


def _cand_year(c: dict) -> int | None:
    """候选年份（取前 4 位）。"""
    y = str(c.get("year") or "")[:4]
    return int(y) if y.isdigit() else None


def _same_title_ids(pool: list[dict], title: str, type_hint: str, *, year: str | None) -> set[int]:
    """按「归一化标题相等」求同一部作品的候选 id 集合。

    规则（客观、可复现）:
        - 标题归一化后必须完全相等（复用生产的 ``_normalize``）
        - 类型已知（movie/tv）时类型必须一致
        - ``year`` 传入时不额外过滤年份；年份只由 :func:`_truth_l1` 处理
    集合为空 = 候选里没有这部作品 → 正确行为是「拒绝」。
    """
    norm = _normalize(title.strip().lower())
    out: set[int] = set()
    for c in pool:
        if _normalize(str(c.get("title") or "").lower()) != norm:
            continue
        if type_hint in ("movie", "tv") and str(c.get("type") or "").lower() != type_hint:
            continue
        out.add(int(c["id"]))
    return out


def _truth_l1(pool: list[dict], ids: set[int], year: str | None) -> set[int]:
    """年份严格变体（敏感性分析用）：源年份已知时要求候选年份差 ≤ 1 年。

    注意 TMDB 的年份是上映年，豆瓣年份常是首映/参赛年（如「寒战1994」标题自带 1994），
    因此该变体会把同名的真作品误判为不同作品 —— 仅作敏感性对照，不作为主口径。
    """
    want_year = int(year) if year and str(year)[:4].isdigit() else None
    if want_year is None:
        return set(ids)
    return {
        int(c["id"])
        for c in pool
        if int(c["id"]) in ids and isinstance(c.get("year"), int) and abs(c["year"] - want_year) <= _YEAR_TOLERANCE
    }


async def _load_unsubscribed(db) -> set[str]:
    """读取被退订的标题集合（弱负标签用）。"""
    rows = await db.execute(text("select message from activity_logs where action = 'unsubscribe'"))
    titles: set[str] = set()
    for (msg,) in rows.all():
        # 消息形如「取消订阅 <标题>」
        t = re.sub(r"^取消订阅[:：\s]*", "", (msg or "").strip()).strip()
        if t:
            titles.add(t)
    return titles


async def _load_auto_sub_logs(db) -> list[tuple[str, str]]:
    """读 activity_logs 的自动订阅记录（标题, 时间），用于交叉核对样本覆盖。"""
    rows = await db.execute(
        text(
            "select message, to_char(created_at, 'YYYY-MM-DD HH24:MI:SS') from activity_logs "
            "where action = 'subscribe' and message like '自动订阅:%' order by created_at"
        )
    )
    out: list[tuple[str, str]] = []
    for msg, ts in rows.all():
        m = re.match(r"^自动订阅:\s*(.+?)\s*\((movie|tv)\)\s*$", msg or "")
        if m:
            out.append((m.group(1), ts))
    return out


def _load_samples(handled: dict, unsub: set[str]) -> list[dict]:
    """把 handled 历史展开成回放样本。"""
    samples: list[dict] = []
    for seed, entry in sorted(handled.items()):
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        type_hint = entry.get("media_type") if entry.get("media_type") in ("movie", "tv") else "all"
        samples.append(
            {
                "id": seed,
                "source_title": title,
                "seed_base_title": _base_title(seed),
                "source_year": _seed_year(seed),
                "type_hint": type_hint,
                "source": entry.get("source"),
                "status": entry.get("status"),
                "hist_tmdb_id": entry.get("tmdb_id"),
                "hist_reason": entry.get("reason"),
                "handled_time": entry.get("time"),
                "weak_negative": title in unsub,
            }
        )
    return samples


async def _search_one(sample: dict, cache: dict, nf, tmdb, sem: asyncio.Semaphore) -> None:
    """重建单个样本的候选池（复用生产搜索链路，关闭 fallback/AI）。"""
    key = f"{sample['source_title']}|{sample['type_hint']}"
    if key in cache:
        pool = cache[key]
    else:
        async with sem:
            queries = build_search_queries(sample["source_title"])
            try:
                results, _variant_map = await _search_with_variants(queries, sample["type_hint"], nf, tmdb)
            except Exception as exc:  # noqa: BLE001 — 单条失败不拖垮整批，显式记录
                sample["search_error"] = f"{type(exc).__name__}: {exc}"
                results = None
        results = results or []
        # 与 pick_best 同口径：类型明确时先用同类型候选，为空才回退全部
        typed = [r for r in results if _cand_type(r) == sample["type_hint"]]
        pool = typed or results if sample["type_hint"] in ("movie", "tv") else results
        cache[key] = pool
    sample["queries"] = build_search_queries(sample["source_title"])
    sample["pool"] = [
        {
            "id": int(c["id"]),
            "title": _cand_title(c),
            "year": _cand_year(c),
            "type": _cand_type(c),
            "vote": c.get("vote_average"),
        }
        for c in pool
    ]


def _decide_a(sample: dict) -> None:
    """A 侧：现有启发式（pick_best + title_similar_enough）。"""
    pool = sample["pool"]
    raw = [
        {"id": c["id"], "title": c["title"], "year": c["year"], "raw_type": c["type"], "vote_average": c["vote"]}
        for c in pool
    ]
    pick = pick_best(raw, sample["source_title"], sample["type_hint"], sample["source_year"])
    similar = bool(pick) and title_similar_enough(sample["source_title"], pick.get("title") or "")
    sample["a_pick_id"] = int(pick["id"]) if pick else None
    sample["a_pick_title"] = (pick.get("title") or "") if pick else None
    sample["a_similar"] = similar
    sample["a_accept"] = bool(pick) and similar


def _label(sample: dict) -> None:
    """真值标签：候选池里是否存在「同一部作品」。

    主口径 L2：归一化标题相等（+ 类型一致，类型已知时），年份不参与判定。
    敏感性口径 L1：在 L2 基础上额外要求年份差 ≤ 1（源年份已知时）。
    """
    ids = _same_title_ids(sample["pool"], sample["source_title"], sample["type_hint"], year=sample["source_year"])
    ids_l1 = _truth_l1(sample["pool"], ids, sample["source_year"])
    sample["truth_ids"] = sorted(ids)
    sample["truth_ids_yearstrict"] = sorted(ids_l1)
    sample["truth_present"] = bool(ids)
    sample["truth_present_yearstrict"] = bool(ids_l1)
    sample["label"] = "accept" if ids else "reject"
    sample["n_same_title"] = len(ids)
    # 同名多候选（源年份缺失时 A 只能在评分上做取舍）→ 单列子群
    sample["year_ambiguous"] = len(ids) > 1 and sample["source_year"] is None
    # 高置信负样本：候选池里连「同名候选」都没有，A 若采纳必然是模糊匹配
    sample["no_same_title"] = not ids
    sample["a_correct"] = (sample["a_accept"] and sample["a_pick_id"] in ids) or (not sample["a_accept"] and not ids)
    sample["a_correct_yearstrict"] = (sample["a_accept"] and sample["a_pick_id"] in ids_l1) or (
        not sample["a_accept"] and not ids_l1
    )
    sample["a_matched_history"] = sample["hist_tmdb_id"] is not None and sample["a_pick_id"] == sample["hist_tmdb_id"]
    sample["hist_in_pool"] = sample["hist_tmdb_id"] is not None and any(
        c["id"] == sample["hist_tmdb_id"] for c in sample["pool"]
    )


def _build_state(sample: dict) -> dict:
    """构造 JEV state —— 只放真实字段，禁止任何人工标注/元信息。"""
    return {
        "待订阅": {
            "标题": sample["source_title"],
            "年份": sample["source_year"],
            "类型": sample["type_hint"] if sample["type_hint"] in ("movie", "tv") else "未知",
        },
        "搜索结果": [
            {"序号": i + 1, "标题": c["title"], "年份": c["year"], "类型": c["type"], "评分": c["vote"]}
            for i, c in enumerate(sample["pool"])
        ],
    }


def _questions(max_pool: int) -> dict:
    """构造批量回放的问题集合（criteria 用序号键，逐行通用）。"""
    criteria = {f"cand_{i}": f"候选{i}" for i in range(1, max_pool + 1)}
    criteria["none"] = "以上都不是同一部作品"
    return {
        "same_work__0": {
            "type": "noul",
            "instructions": (
                "『待订阅』中的条目与『搜索结果』里是否存在同一部作品？"
                "同名但年份、类型或版本（电影版/剧集版、剧场版/TV版、同一IP的不同季）不同，视为不同作品。"
                "搜索结果里没有同一部作品时，答案为不成立。"
            ),
        },
        "which__0": {
            "type": "choice",
            "instructions": "哪个候选是『待订阅』指向的那部作品？没有同一部作品时选 none。",
            "criteria": criteria,
        },
    }


async def main() -> int:
    """导出样本、重建候选集、跑 A 侧决策并写出回放输入。"""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    handled = history.get("handled", {})

    async with async_session() as db:
        unsub = await _load_unsubscribed(db)
        auto_logs = await _load_auto_sub_logs(db)
        tmdb = await get_tmdb_service(db)
        nf = await get_nf_service(db)
        if tmdb is None or nf is None:
            print("ERR: tmdb/nextfind 平台未配置，无法重建候选集", file=sys.stderr)
            return 2

    samples = _load_samples(handled, unsub)
    print(
        f"handled 条目 {len(handled)} → 可用样本 {len(samples)}；退订标题 {len(unsub)}；自动订阅日志 {len(auto_logs)}"
    )

    cache: dict = json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {}
    sem = asyncio.Semaphore(_MAX_CONCURRENCY)
    await asyncio.gather(*[_search_one(s, cache, nf, tmdb, sem) for s in samples])
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    for s in samples:
        _decide_a(s)
        _label(s)

    total = len(samples)
    pos = sum(1 for s in samples if s["truth_present"])
    err = sum(1 for s in samples if s.get("search_error"))
    empty = sum(1 for s in samples if not s["pool"])
    print(f"样本 {total}：候选非空 {total - empty}、空候选 {empty}、搜索异常 {err}")
    print(f"真值：有同一部作品 {pos} / 无 {total - pos}")
    print(
        f"A 侧准确 {sum(1 for s in samples if s['a_correct'])} / {total}；与历史匹配一致 {sum(1 for s in samples if s['a_matched_history'])}"
    )
    print("历史状态分布:", Counter(s["status"] for s in samples).most_common())

    max_pool = max((len(s["pool"]) for s in samples), default=0)
    # items.jsonl 每行就是 state 本身（jev.py map 默认整行作为 state），按 state 去重，
    # 样本与行之间用 state 的规范化哈希对应（见 items_manifest.json）。
    uniq: dict[str, dict] = {}
    for s in samples:
        state = _build_state(s)
        digest = hashlib.sha1(json.dumps(state, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        s["state_hash"] = digest
        uniq.setdefault(digest, state)
    manifest = list(uniq.keys())
    (OUT_DIR / "samples.json").write_text(json.dumps(samples, ensure_ascii=False), encoding="utf-8")
    with (OUT_DIR / "items.jsonl").open("w", encoding="utf-8") as f:
        for digest in manifest:
            f.write(json.dumps(uniq[digest], ensure_ascii=False) + "\n")
    (OUT_DIR / "items_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "questions.json").write_text(
        json.dumps(_questions(max_pool), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"写出 {OUT_DIR}/samples.json、items.jsonl（{len(manifest)} 行去重 state）、questions.json（max_pool={max_pool}）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
