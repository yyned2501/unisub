"""自动订阅候选池与未识别归因测试 — S1（池化/精确优先/相似度门槛/JEV 顺序）+ S5（归因）。

覆盖 `docs/SPEC-MATCHING-RECALL.md` §3B 的四类验收：
    ① 全名出垃圾、基础变体有精确命中 → 必须选精确命中
    ② 相似度不过的候选不进池
    ③ 变体全不中 → reason 正确
    ④ AI 空返回 → WARN 日志 + ai_empty
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.auto_subscribe.models import (
    REASON_AI_EMPTY,
    REASON_GATE_REJECT,
    REASON_NO_CANDIDATES,
    REASON_SIMILARITY_REJECT,
    RankMediaItem,
)
from app.services.auto_subscribe.pipeline import matching, resolve, search
from app.services.auto_subscribe.pipeline.search import FallbackOutcome
from app.services.decision.engine import GateResult, GateVerdict

# 搜索/闸门/fallback 全部被替身接管，这里不需要真实服务
NF: Any = None

# 故意不相似的垃圾候选（TMDB 模糊匹配全名时的真实返回）
GARBAGE = [
    {"id": 9001, "title": "乱马½", "media_type": "tv", "year": 2025, "vote_average": 8.1},
    {"id": 9002, "title": "坠落2：死点", "media_type": "tv", "year": 2024, "vote_average": 7.5},
]


def _item(title: str, type_hint: str = "tv", year: str | None = None) -> RankMediaItem:
    """构造待订阅条目（不带 bangumi_id，避免触发 Bangumi 网络调用）。"""
    return RankMediaItem(
        title=title,
        year=year,
        type_hint=type_hint,
        source_meta={"source": "mikan"},
        unique_seed=f"mikan:{title}",
    )


def _cand(title: str, year: int | None = None, media_type: str = "tv", cid: int = 1) -> dict[str, Any]:
    """构造候选（字段形状与 TMDB/NF 搜索结果一致）。"""
    return {"id": cid, "title": title, "media_type": media_type, "year": year, "vote_average": 7.0}


def _patch_search(monkeypatch: pytest.MonkeyPatch, mapping: dict[tuple[str, str], list[dict]]) -> None:
    """按 (搜索词, 类别) 返回结果的搜索替身。"""

    async def fake_search(query: str, search_type: str, nf: Any, tmdb: Any) -> list[dict]:
        return mapping.get((query, search_type), [])

    monkeypatch.setattr(resolve, "search_tmdb_or_nf", fake_search)


def _patch_fallback(monkeypatch: pytest.MonkeyPatch, outcome: FallbackOutcome) -> None:
    """把 fallback 链替换成固定结论。"""

    async def fake_chain(*args: Any, **kwargs: Any) -> FallbackOutcome:
        return outcome

    monkeypatch.setattr(resolve, "run_fallback_chain", fake_chain)


def _patch_gate(monkeypatch: pytest.MonkeyPatch, verdict: GateVerdict, shadow: bool = False) -> list[dict]:
    """把 JEV 闸门替换成固定判定，返回调用记录列表（断言是否真的问过闸门）。"""
    calls: list[dict] = []

    async def fake_evaluate(title: str, year: Any, type_hint: str, candidate: dict) -> GateResult:
        calls.append({"title": title, "candidate": candidate.get("title")})
        return GateResult(verdict=verdict, same_work=0.9 if verdict is GateVerdict.PASS else 0.1, shadow=shadow)

    monkeypatch.setattr(matching, "evaluate_candidate", fake_evaluate)
    return calls


# ── ① 候选池 + 精确优先 ─────────────────────────────────────


async def test_pool_prefers_exact_hit_over_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    """全名搜索出一堆垃圾、基础变体有精确命中时必须选精确命中（R1）。"""
    title = "弹珠汽水瓶里的千岁同学 第2部分"
    exact = _cand("弹珠汽水瓶里的千岁同学", year=2025)
    _patch_search(
        monkeypatch,
        {
            (title, "tv"): GARBAGE,
            ("弹珠汽水瓶里的千岁同学", "tv"): [exact],
        },
    )
    _patch_fallback(monkeypatch, FallbackOutcome())
    gate_calls = _patch_gate(monkeypatch, GateVerdict.DISABLED)

    outcome = await resolve.resolve_best_match(_item(title), "tv", NF, None)

    assert outcome.best is exact
    assert outcome.variant == "弹珠汽水瓶里的千岁同学"
    assert gate_calls == []  # 精确命中不花 JEV 的钱


async def test_garbage_candidates_do_not_enter_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    """相似度不过的垃圾候选不进池，不能掩盖后面的精确命中（R2）。"""
    title = "怪兽8号 鸣海的平日"
    hit = _cand("怪兽8号", year=2024)
    _patch_search(
        monkeypatch,
        {
            (title, "tv"): GARBAGE,
            ("怪兽8号", "tv"): [hit],
        },
    )
    _patch_fallback(monkeypatch, FallbackOutcome())
    _patch_gate(monkeypatch, GateVerdict.REJECT)  # 闸门若被问到会拦，用于证明精确命中没走闸门

    outcome = await resolve.resolve_best_match(_item(title), "tv", NF, None)

    assert outcome.best is hit
    assert outcome.variant == "怪兽8号"


async def test_similarity_ranking_prevents_false_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    """池里先入池的是垃圾候选，但正确候选字面更像 → 必须选正确候选。

    线上实测：全名变体被 TMDB 模糊匹配成 10 条无关片（其中《破产姐妹》只因
    「姐妹」两字相同就通过了 30% 相似度门槛），基础变体才返回正确的
    《魔法姐妹露露和莉莉》。不按相似度重排时，阶段 3「年份就近」会在年份打平
    时按入池顺序选中《破产姐妹》→ 误订。
    """
    title = "魔法姐妹露露特莉莉 第2部分"
    garbage = [_cand("坠落2：死点", year=2026, cid=11), _cand("破产姐妹", year=2011, cid=12)]
    hit = _cand("魔法姐妹露露和莉莉", year=2026, cid=13)
    _patch_search(monkeypatch, {(title, "tv"): garbage, ("魔法姐妹露露特莉莉", "tv"): [hit]})
    _patch_fallback(monkeypatch, FallbackOutcome())
    _patch_gate(monkeypatch, GateVerdict.DISABLED)

    outcome = await resolve.resolve_best_match(_item(title), "tv", NF, None)

    assert outcome.best is hit
    assert outcome.variant == "魔法姐妹露露特莉莉"


async def test_fallback_pool_is_used_when_main_pool_misses(monkeypatch: pytest.MonkeyPatch) -> None:
    """主池全不中时用 fallback 链（Bangumi 原名/别名）的候选池（S3 收尾）。"""
    title = "东京复仇者 三天战争篇"
    hit = _cand("东京复仇者", year=2021)
    _patch_search(monkeypatch, {})
    _patch_fallback(monkeypatch, FallbackOutcome(results=[hit], variant_map={"1": "東京リベンジャーズ"}))
    _patch_gate(monkeypatch, GateVerdict.DISABLED)

    outcome = await resolve.resolve_best_match(_item(title), "tv", NF, None)

    assert outcome.best is hit
    assert outcome.variant == "東京リベンジャーズ"


# ── JEV 与相似度的顺序（新增裁决） ───────────────────────────


async def test_gate_pass_overrides_similarity_veto(monkeypatch: pytest.MonkeyPatch) -> None:
    """JEV 判同一部作品时不得再被字面相似度否决（译名差异类召回）。"""
    title = "东京复仇者 三天战争篇"
    hit = _cand("重生之道", year=2021)
    _patch_search(monkeypatch, {("东京复仇者", "tv"): [hit], (title, "tv"): []})
    _patch_fallback(monkeypatch, FallbackOutcome())
    calls = _patch_gate(monkeypatch, GateVerdict.PASS)

    outcome = await resolve.resolve_best_match(_item(title), "tv", NF, None)

    assert outcome.best is hit
    assert calls and calls[0]["candidate"] == "重生之道"


async def test_gate_pass_in_shadow_does_not_override_similarity(monkeypatch: pytest.MonkeyPatch) -> None:
    """影子判定不算数：否则等于重新放开误订。"""
    title = "东京复仇者 三天战争篇"
    _patch_search(monkeypatch, {("东京复仇者", "tv"): [_cand("重生之道", year=2021)]})
    _patch_fallback(monkeypatch, FallbackOutcome())
    _patch_gate(monkeypatch, GateVerdict.PASS, shadow=True)

    outcome = await resolve.resolve_best_match(_item(title), "tv", NF, None)

    assert outcome.best is None
    assert outcome.reason == REASON_SIMILARITY_REJECT


# ── ③ 归因 reason / variant / top_candidates ────────────────


async def test_reason_no_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    """一个候选都没有 → no_candidates，且不留候选标题。"""
    _patch_search(monkeypatch, {})
    _patch_fallback(monkeypatch, FallbackOutcome())

    outcome = await resolve.resolve_best_match(_item("巴黎绽放的星辰"), "tv", NF, None)

    assert outcome.best is None
    assert outcome.reason == REASON_NO_CANDIDATES
    assert outcome.top_candidates == []


async def test_reason_similarity_reject_with_attribution(monkeypatch: pytest.MonkeyPatch) -> None:
    """有候选但全不相似 → similarity_reject，并带搜索词与候选标题。"""
    title = "神秘面包小子"
    _patch_search(monkeypatch, {(title, "tv"): GARBAGE})
    _patch_fallback(monkeypatch, FallbackOutcome())
    _patch_gate(monkeypatch, GateVerdict.DISABLED)

    outcome = await resolve.resolve_best_match(_item(title), "tv", NF, None)

    assert outcome.best is None
    assert outcome.reason == REASON_SIMILARITY_REJECT
    assert outcome.variant == title
    assert outcome.top_candidates == ["乱马½", "坠落2：死点"]


async def test_reason_gate_reject(monkeypatch: pytest.MonkeyPatch) -> None:
    """候选进了池（相似度过）但阶段 4/5 被 JEV 判非同一作品 → gate_reject。"""
    title = "东京复仇者 三天战争篇"
    _patch_search(monkeypatch, {("东京复仇者", "tv"): [_cand("东京复仇者", year=2021)]})
    _patch_fallback(monkeypatch, FallbackOutcome())
    _patch_gate(monkeypatch, GateVerdict.REJECT)

    # 条目年份 2026 与候选 2021 相差 >1 年，落不到阶段 1~3，必须问闸门
    outcome = await resolve.resolve_best_match(_item(title, "tv", year="2026"), "tv", NF, None)

    assert outcome.best is None
    assert outcome.reason == REASON_GATE_REJECT
    assert outcome.top_candidates == ["东京复仇者"]


async def test_reason_similarity_reject_when_gate_also_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    """候选既不过字面相似度、JEV 也判非同一作品 → similarity_reject（可归因）。"""
    title = "深海幽灵"
    _patch_search(monkeypatch, {(title, "movie"): [_cand("海上钢琴师", year=1998, media_type="movie")]})
    _patch_fallback(monkeypatch, FallbackOutcome())
    _patch_gate(monkeypatch, GateVerdict.REJECT)

    outcome = await resolve.resolve_best_match(_item(title, "movie"), "movie", NF, None)

    assert outcome.best is None
    assert outcome.reason == REASON_SIMILARITY_REJECT
    assert outcome.top_candidates == ["海上钢琴师"]


async def test_reason_ai_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """AI 兜底被调用但没产出结果 → ai_empty（区分「压根没候选」）。"""
    _patch_search(monkeypatch, {})
    _patch_fallback(monkeypatch, FallbackOutcome(ai_failed=True))

    outcome = await resolve.resolve_best_match(_item("巴黎绽放的星辰"), "tv", NF, None)

    assert outcome.best is None
    assert outcome.reason == REASON_AI_EMPTY


async def test_ai_failure_does_not_mask_rejected_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    """主池有候选但全被否、AI 兜底也失败 → 归因仍是 similarity_reject（线上实测错报过 ai_empty）。"""
    title = "神秘面包小子"
    _patch_search(monkeypatch, {(title, "tv"): GARBAGE})
    _patch_fallback(monkeypatch, FallbackOutcome(ai_failed=True))
    _patch_gate(monkeypatch, GateVerdict.DISABLED)

    outcome = await resolve.resolve_best_match(_item(title), "tv", NF, None)

    assert outcome.reason == REASON_SIMILARITY_REJECT
    assert outcome.top_candidates == ["乱马½", "坠落2：死点"]


# ── ④ AI 兜底：空返回落 WARN + reasoning 兜底 ──────────────


class _FakeHttp:
    """替身 HTTP 客户端：返回脚本化的 chat/completions 响应。"""

    def __init__(self, message: dict) -> None:
        self.message = message
        self.calls: list[dict] = []

    async def post(self, url: str, headers: dict | None = None, json: dict | None = None) -> Any:
        self.calls.append({"url": url, "json": json or {}})
        return {"choices": [{"message": self.message}]}


def _use_ai_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """把 AI 配置指向临时文件并开启 AI 兜底。"""
    from app.services.ai_config import AiConfigStore

    store = AiConfigStore(config_path=tmp_path / "ai_config.json", legacy_config_path=tmp_path / "legacy.json")
    store.save_config({"ai_assist_enabled": True, "ai_api_key": "k", "ai_api_base": "http://ai.test", "ai_model": "m"})
    monkeypatch.setattr(search, "get_ai_config_store", lambda: store)


async def test_ai_empty_content_logs_warning_and_flags_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """AI 空返回必须落 WARN 日志并置 ai_failed（原来全静默）。"""
    _use_ai_config(monkeypatch, tmp_path)
    fake = _FakeHttp({"content": "", "reasoning_content": ""})
    monkeypatch.setattr(search, "http_client", fake)

    with caplog.at_level("WARNING"):
        pool, variant_map, ai_failed = await search._ai_assisted_search(
            "巴黎绽放的星辰", _item("巴黎绽放的星辰"), "tv", None, None
        )

    assert (pool, variant_map) == ([], {})
    assert ai_failed is True
    assert any("AI 兜底失败" in r.getMessage() and "空返回" in r.getMessage() for r in caplog.records)
    assert fake.calls[0]["json"]["model"] == "m"


async def test_ai_reasoning_content_fallback_extracts_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """content 为空时从 reasoning_content 里提取 JSON 再兜一次（推理模型实测行为）。"""
    _use_ai_config(monkeypatch, tmp_path)
    fake = _FakeHttp(
        {"content": "", "reasoning_content": '先说一堆话…… {"title": "怪兽8号", "media_type": "tv", "season": null}'}
    )
    monkeypatch.setattr(search, "http_client", fake)
    hit = _cand("怪兽8号", year=2024)

    async def fake_search(query: str, search_type: str, nf: Any, tmdb: Any) -> list[dict]:
        return [hit] if query == "怪兽8号" else []

    monkeypatch.setattr(search, "search_tmdb_or_nf", fake_search)

    pool, variant_map, ai_failed = await search._ai_assisted_search(
        "怪兽8号 鸣海的平日", _item("怪兽8号 鸣海的平日"), "tv", NF, None
    )

    assert ai_failed is False
    assert pool == [hit]
    assert variant_map == {"1": "怪兽8号"}


async def test_ai_search_failure_logs_and_does_not_fabricate(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """AI 识别成功但回搜无结果 → 不伪造命中，落 WARN，归因给 no_candidates（不是 AI 故障）。

    线上实测：`神秘面包小子` 的 AI 识别结果就是它自己，TMDB 确实没有这个条目 ——
    这是「TMDB 无此条目」，不是「AI 坏了」，所以 ``ai_failed`` 保持 False。
    """
    _use_ai_config(monkeypatch, tmp_path)
    monkeypatch.setattr(search, "http_client", _FakeHttp({"content": '{"title": "不存在的片", "media_type": "tv"}'}))

    async def fake_search(query: str, search_type: str, nf: Any, tmdb: Any) -> list[dict]:
        return []

    monkeypatch.setattr(search, "search_tmdb_or_nf", fake_search)

    pool, _variant_map, ai_failed = await search._ai_assisted_search(
        "神秘面包小子", _item("神秘面包小子"), "tv", NF, None
    )

    assert pool == []
    assert ai_failed is False


async def test_ai_search_no_result_maps_to_no_candidates(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """AI 回搜无候选 → 归因 no_candidates（TMDB 无此条目），且不静默丢。"""
    _use_ai_config(monkeypatch, tmp_path)
    monkeypatch.setattr(search, "http_client", _FakeHttp({"content": '{"title": "神秘面包小子", "media_type": "tv"}'}))

    async def fake_search(query: str, search_type: str, nf: Any, tmdb: Any) -> list[dict]:
        return []

    monkeypatch.setattr(search, "search_tmdb_or_nf", fake_search)
    calls = _patch_gate(monkeypatch, GateVerdict.DISABLED)
    _patch_search(monkeypatch, {})

    outcome = await resolve.resolve_best_match(_item("神秘面包小子"), "tv", NF, None)

    assert outcome.best is None
    assert outcome.reason == REASON_NO_CANDIDATES
    assert calls == []


# ── ⑤ AI 结果与原标题字面不重叠（疑换作品）→ 必须 JEV 背书 ─────


def test_ai_pool_low_overlap_detection() -> None:
    """重叠不足 0.5 的 AI 候选池被标记（实测 巴黎绽放的星辰 ↔ 艾米丽在巴黎 只共享「巴黎」）。"""
    assert search._is_low_overlap_pool("巴黎绽放的星辰", [_cand("艾米丽在巴黎", year=2020)]) is True
    assert search._is_low_overlap_pool("杀手旅店 第二季", [_cand("异人旅馆", year=2025)]) is True
    assert search._is_low_overlap_pool("怪兽8号 鸣海的平日", [_cand("怪兽8号", year=2024)]) is False


async def test_ai_low_overlap_pool_dropped_when_gate_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """AI 认错作品（巴黎绽放的星辰 → 艾米丽在巴黎）+ JEV 降级 → 不采纳，归因 no_candidates。

    两者只共享「巴黎」两字（重叠 0.33），30% 的字面门槛拦不住 —— 这正是线上会误订的路径。
    JEV 不可用时无法确认是否同一部作品 → 整池丢弃，不许伪造命中。
    """
    title = "巴黎绽放的星辰"
    _patch_search(monkeypatch, {})
    _patch_fallback(
        monkeypatch,
        FallbackOutcome(
            results=[_cand("艾米丽在巴黎", year=2020)], variant_map={"1": "Emily in Paris"}, ai_low_overlap=True
        ),
    )
    _patch_gate(monkeypatch, GateVerdict.FALLBACK)

    outcome = await resolve.resolve_best_match(_item(title, "all"), "all", NF, None)

    assert outcome.best is None
    assert outcome.reason == REASON_NO_CANDIDATES
    assert outcome.top_candidates == []


async def test_ai_low_overlap_pool_accepted_when_gate_confirms(monkeypatch: pytest.MonkeyPatch) -> None:
    """AI 给出译名（字面不像）但 JEV 明确判同一部作品 → 采纳（译名差异类召回）。"""
    title = "杀手旅店 第二季"
    hit = _cand("异人旅馆", year=2025)
    _patch_search(monkeypatch, {})
    _patch_fallback(monkeypatch, FallbackOutcome(results=[hit], variant_map={"1": "异人旅馆"}, ai_low_overlap=True))
    calls = _patch_gate(monkeypatch, GateVerdict.PASS)

    outcome = await resolve.resolve_best_match(_item(title), "tv", NF, None)

    assert outcome.best is hit
    assert outcome.variant == "异人旅馆"
    assert calls and calls[0]["candidate"] == "异人旅馆"


async def test_ai_low_overlap_pool_rejected_by_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """JEV 判「不是同一部作品」→ 不采纳，归因 no_candidates。"""
    title = "巴黎绽放的星辰"
    _patch_search(monkeypatch, {})
    _patch_fallback(monkeypatch, FallbackOutcome(results=[_cand("艾米丽在巴黎", year=2020)], ai_low_overlap=True))
    _patch_gate(monkeypatch, GateVerdict.REJECT)

    outcome = await resolve.resolve_best_match(_item(title, "all"), "all", NF, None)

    assert outcome.best is None
    assert outcome.reason == REASON_NO_CANDIDATES
