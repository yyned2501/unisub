"""JEV（TypeSafe System One）采纳闸门 — 自动订阅兜底判定的唯一入口。

边界（`docs/SPEC-JEV-DECISION.md` §1）:
    - 本模块是判定规则的唯一入口；HTTP/配置在 :mod:`app.services.decision.client`，
      state 构造在 :mod:`app.services.decision.payload`；
    - `pipeline/matching.py` 只调用 :func:`evaluate_candidate`，不承担 HTTP、不读配置细节；
    - 无状态：不落库、不建表、不持有会话（除进程内降级计数）。

接入形态（由 Phase 4A 实测定档，见 `docs/jev-replay-report.md` §8）:
    A 侧（启发式）先选出候选 → 只把这 1 个候选交给 JEV 判「是否同一部作品」→
    `same_work >= 阈值` 放行，否则拦截。**不解析 `which`**（单候选形态下实测 21 例
    `same_work >= 0.7` 却 `which = none` 的自相矛盾答案，读它会凭空损失召回）。

降级（本卡最高优先级验收点）:
    JEV 不可用/超时/HTTP 异常/字段缺失 → **回退旧启发式继续跑**（不因为 JEV 挂了就
    改变下单行为），**同时** `logger.error` + 进程内降级计数（`get_gate_metrics()`），
    供后续查「降级发生了多久」；连续失败达阈值即熔断，冷却期内不再发起请求。
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from app.core.logger import init_logger
from app.services.decision.client import call_jev, extract_same_work, load_gate_config
from app.services.decision.payload import build_questions, build_state, candidate_title

logger = init_logger()

# 熔断：连续失败达阈值后暂停调用，冷却期满自动半开重试
_BREAKER_THRESHOLD = 5
_BREAKER_COOLDOWN_S = 600.0

# 中间区间上界：`< 阈值` 拦截；[阈值, 0.7) 保留启发式结果并 warn（双重确认，不叠加两个风险）
_MID_ZONE_WARN_UPPER = 0.7


class GateVerdict(StrEnum):
    """闸门结论。"""

    DISABLED = "disabled"
    """开关关闭，未调用 JEV（沿用启发式结果）。"""

    PASS = "pass"
    """放行：保留 A 侧（启发式）选中的候选。"""

    REJECT = "reject"
    """拦截：A 侧候选与待订阅不是同一部作品，应放弃订阅。"""

    FALLBACK = "fallback"
    """JEV 不可用 → 回退旧启发式（等价放行），已计入降级。"""


@dataclass(frozen=True)
class GateResult:
    """一次闸门判定的结果。"""

    verdict: GateVerdict
    same_work: float | None = None
    model: str | None = None
    elapsed_s: float | None = None
    reason: str = ""
    shadow: bool = False


@dataclass
class _GateMetrics:
    """进程内降级/调用计数（`get_gate_metrics()` 暴露，供排查「降级持续多久」）。"""

    calls: int = 0
    passed: int = 0
    rejected: int = 0
    fallbacks: int = 0
    shadow_calls: int = 0
    consecutive_failures: int = 0
    breaker_open_until: float = 0.0


_metrics = _GateMetrics()


def get_gate_metrics() -> dict[str, Any]:
    """返回 JEV 闸门的进程内计数快照（调用数、拦截数、降级数、熔断状态）。"""
    snapshot: dict[str, Any] = asdict(_metrics)
    now = time.monotonic()
    snapshot["breaker_open"] = _metrics.breaker_open_until > now
    snapshot["breaker_remaining_s"] = max(0.0, round(_metrics.breaker_open_until - now, 1))
    return snapshot


def reset_gate_state() -> None:
    """重置进程内计数与熔断状态（供测试与排障使用）。"""
    global _metrics
    _metrics = _GateMetrics()


async def evaluate_candidate(
    source_title: str,
    source_year: str | int | None,
    type_hint: str,
    candidate: dict,
) -> GateResult:
    """判定「A 侧选中的唯一候选」是否与待订阅条目是同一部作品。

    Args:
        source_title: 待订阅条目的标题（榜单源原文，不做归一化改写）
        source_year: 待订阅条目的年份（可空）
        type_hint: 待订阅条目的类型提示（movie / tv / all）
        candidate: A 侧选中的候选（搜索结果的原始 dict）

    Returns:
        :class:`GateResult`。仅在 ``REJECT`` 时调用方应放弃该候选；
        ``DISABLED`` / ``PASS`` / ``FALLBACK`` 都保留启发式结果。
    """
    cfg = load_gate_config()
    if not cfg.enabled:
        return GateResult(verdict=GateVerdict.DISABLED, reason="开关未启用")
    if not source_title.strip():
        return GateResult(verdict=GateVerdict.DISABLED, reason="待订阅标题为空，跳过闸门")

    if _metrics.breaker_open_until > time.monotonic():
        return _degrade(
            f"熔断中（连续失败 {_metrics.consecutive_failures} 次，剩余 "
            f"{_metrics.breaker_open_until - time.monotonic():.0f}s）"
        )

    state = build_state(source_title, source_year, type_hint, candidate)
    response, error, elapsed = await call_jev(cfg, state, build_questions())
    if error is not None:
        return _degrade(error)
    if response is None:
        return _degrade("响应为空")

    same_work = extract_same_work(response)
    if same_work is None:
        return _degrade("响应缺少 same_work__0.noul 字段")

    _on_success()
    model = str(response.get("model") or cfg.model)
    raw_usage = response.get("usage")
    usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
    rejected = same_work < cfg.threshold
    logger.info(
        "JEV 判定: 待订阅=%s 候选=%s same_work=%.3f 阈值=%.2f 结论=%s model=%s 耗时=%.3fs "
        "input_tokens=%s output_tokens=%s",
        source_title,
        candidate_title(candidate),
        same_work,
        cfg.threshold,
        "reject" if rejected else "pass",
        model,
        elapsed,
        usage.get("input_tokens"),
        usage.get("output_tokens"),
    )

    if cfg.shadow:
        _metrics.shadow_calls += 1
        logger.info(
            "JEV 影子判定: 概率=%.3f 阈值=%.2f 本会拦截=%s 实际采纳=True 待订阅=%s 候选=%s（影子，不生效）",
            same_work,
            cfg.threshold,
            rejected,
            source_title,
            candidate_title(candidate),
        )
        return GateResult(
            verdict=GateVerdict.PASS,
            same_work=same_work,
            model=model,
            elapsed_s=elapsed,
            reason="shadow",
            shadow=True,
        )

    if rejected:
        _metrics.rejected += 1
        logger.warning(
            "JEV 采纳闸门拦截: 待订阅=%s 候选=%s same_work=%.3f < %.2f，放弃该候选",
            source_title,
            candidate_title(candidate),
            same_work,
            cfg.threshold,
        )
        return GateResult(
            verdict=GateVerdict.REJECT,
            same_work=same_work,
            model=model,
            elapsed_s=elapsed,
            reason="below_threshold",
        )

    _metrics.passed += 1
    if same_work < _MID_ZONE_WARN_UPPER:
        logger.warning(
            "JEV 判定处于中间区间: 待订阅=%s 候选=%s same_work=%.3f（阈值 %.2f），保留启发式结果",
            source_title,
            candidate_title(candidate),
            same_work,
            cfg.threshold,
        )
    return GateResult(verdict=GateVerdict.PASS, same_work=same_work, model=model, elapsed_s=elapsed)


def _degrade(reason: str) -> GateResult:
    """记录一次可见降级：`logger.error` + 计数 + 连续失败熔断。"""
    _metrics.calls += 1
    _metrics.fallbacks += 1
    _metrics.consecutive_failures += 1
    logger.error("JEV 不可用，回退启发式: %s", reason)
    if _metrics.consecutive_failures >= _BREAKER_THRESHOLD and _metrics.breaker_open_until <= time.monotonic():
        _metrics.breaker_open_until = time.monotonic() + _BREAKER_COOLDOWN_S
        logger.error(
            "JEV 连续失败 %d 次，熔断 %.0f 秒（期间回退启发式，不再发起请求）",
            _metrics.consecutive_failures,
            _BREAKER_COOLDOWN_S,
        )
    return GateResult(verdict=GateVerdict.FALLBACK, reason=reason)


def _on_success() -> None:
    """一次成功调用：计数 + 复位连续失败（熔断自动半开恢复）。"""
    _metrics.calls += 1
    if _metrics.consecutive_failures:
        logger.warning("JEV 调用恢复成功（此前连续失败 %d 次）", _metrics.consecutive_failures)
    _metrics.consecutive_failures = 0
    _metrics.breaker_open_until = 0.0
