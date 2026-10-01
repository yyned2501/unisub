"""JEV 采纳闸门测试 — 开关、影子、阈值、降级回退、熔断与红线段言。

覆盖 `docs/SPEC-JEV-DECISION.md` 的验收点：开关默认关、影子只记录不生效、
阈值可配、JEV 不可用/超时/字段缺失一律回退旧启发式且留下可见 error 日志、
连续失败熔断，以及「禁止 jev-latest 别名 / 禁止裸 HTTP 库 / 不解析 which」三条红线。
"""

from __future__ import annotations

import ast
import pathlib
from typing import Any

import pytest

from app.services import decision, decision_client
from app.services.ai_config import DEFAULT_AI_CONFIG, AiConfigStore
from app.services.auto_subscribe.pipeline import matching
from app.services.decision import GateVerdict, evaluate_candidate, get_gate_metrics, reset_gate_state

SOURCE_TITLE = "深海幽灵"
CANDIDATE: dict[str, Any] = {"title": "海上钢琴师", "year": 1998, "raw_type": "movie", "vote_average": 9.3}


class _FakeHttp:
    """替身 HTTP 客户端：记录调用并按脚本返回响应或抛异常。"""

    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[tuple[str, dict, dict]] = []

    async def post(self, url: str, headers: dict | None = None, json: dict | None = None) -> Any:
        self.calls.append((url, headers or {}, json or {}))
        if self.error is not None:
            raise self.error
        return self.response


def _noul(value: float) -> dict[str, Any]:
    """构造一个只含 same_work 的成功响应。"""
    return {
        "model": "jev-1.13.0",
        "answers": {"same_work__0": {"type": "noul", "noul": value}},
        "usage": {"input_tokens": 438, "output_tokens": 23},
    }


def _use_http(monkeypatch: pytest.MonkeyPatch, fake: _FakeHttp) -> _FakeHttp:
    """把闸门用的 http 客户端换成替身。"""
    monkeypatch.setattr(decision_client, "http_client", fake)
    return fake


def _use_config(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, **overrides: Any) -> AiConfigStore:
    """把闸门配置指向临时 ai_config 文件。"""
    store = AiConfigStore(config_path=tmp_path / "ai_config.json", legacy_config_path=tmp_path / "legacy.json")
    store.save_config(
        {
            "jev_decision_enabled": True,
            "jev_decision_shadow": False,
            "jev_api_base": "https://jev.test",
            "jev_api_key": "test-key",
            "jev_model": "jev-1.13.0",
            "jev_same_work_threshold": 0.5,
            **overrides,
        }
    )
    monkeypatch.setattr(decision_client, "get_ai_config_store", lambda: store)
    return store


@pytest.fixture(autouse=True)
def _reset_gate() -> Any:
    """每个用例前后清空进程内计数与熔断状态，避免串味。"""
    reset_gate_state()
    yield
    reset_gate_state()


@pytest.fixture
def _fast_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """重试退避归零，避免用例被 1s/2s 退避拖慢（策略本身由常量断言覆盖）。"""
    monkeypatch.setattr(decision_client, "_BACKOFF_S", (0.0, 0.0))


# ── 开关与影子 ──────────────────────────────────────────────


async def test_disabled_skips_jev_entirely(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """开关关闭时不得发起任何 JEV 调用（默认关）。"""
    _use_config(monkeypatch, tmp_path, jev_decision_enabled=False)
    fake = _use_http(monkeypatch, _FakeHttp(_noul(0.1)))

    result = await evaluate_candidate(SOURCE_TITLE, 2025, "movie", CANDIDATE)

    assert result.verdict is GateVerdict.DISABLED
    assert fake.calls == []
    assert get_gate_metrics()["calls"] == 0


async def test_default_config_has_gate_off_and_shadow_on() -> None:
    """出厂默认：闸门关、影子开、模型 pin 到具体版本、阈值取 §9 标定值。"""
    assert DEFAULT_AI_CONFIG["jev_decision_enabled"] is False
    assert DEFAULT_AI_CONFIG["jev_decision_shadow"] is True
    assert DEFAULT_AI_CONFIG["jev_model"] == "jev-1.13.0"
    assert DEFAULT_AI_CONFIG["jev_same_work_threshold"] == 0.75


async def test_shadow_records_but_keeps_heuristic_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """影子模式：低于阈值的判定只记录，不影响采纳。"""
    _use_config(monkeypatch, tmp_path, jev_decision_shadow=True)
    _use_http(monkeypatch, _FakeHttp(_noul(0.12)))

    result = await evaluate_candidate(SOURCE_TITLE, 2025, "movie", CANDIDATE)

    assert result.verdict is GateVerdict.PASS
    assert result.shadow is True
    metrics = get_gate_metrics()
    assert metrics["shadow_calls"] == 1
    assert metrics["rejected"] == 0


# ── 阈值判定 ────────────────────────────────────────────────


async def test_pass_above_threshold_and_request_shape(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """高概率放行，且请求体只含 A 侧唯一候选、只问 same_work。"""
    _use_config(monkeypatch, tmp_path)
    fake = _use_http(monkeypatch, _FakeHttp(_noul(0.93)))

    result = await evaluate_candidate(SOURCE_TITLE, "2025", "movie", CANDIDATE)

    assert result.verdict is GateVerdict.PASS
    assert result.same_work == 0.93
    url, headers, body = fake.calls[0]
    assert url == "https://jev.test/v1/systemone"
    assert headers["Authorization"] == "Bearer test-key"
    assert body["model"] == "jev-1.13.0"
    assert list(body["state"]) == ["待订阅", "搜索结果"]
    assert len(body["state"]["搜索结果"]) == 1
    assert body["state"]["待订阅"]["类型"] == "movie"
    assert list(body["questions"]) == ["same_work__0"]
    assert "上传年/上映年口径差异也不算不同作品" in body["questions"]["same_work__0"]["instructions"]
    # v3 两条语义（spec §9）：① 纯书写形式差异 → 同作品；② 副标题/版本/季数/类型差异 → 不同作品
    instruction = body["questions"]["same_work__0"]["instructions"]
    assert "纯书写形式的差异，不影响判定" in instruction
    assert "副标题不同" in instruction and "版本不同" in instruction
    assert "季数不同" in instruction and "类型不同" in instruction


async def test_reject_below_threshold(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """低于阈值拦截，并计入拦截计数。"""
    _use_config(monkeypatch, tmp_path)
    _use_http(monkeypatch, _FakeHttp(_noul(0.25)))

    result = await evaluate_candidate(SOURCE_TITLE, 2025, "movie", CANDIDATE)

    assert result.verdict is GateVerdict.REJECT
    assert get_gate_metrics()["rejected"] == 1


async def test_threshold_comes_from_config(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """阈值读自 ai_config（无需发版调整）。"""
    _use_config(monkeypatch, tmp_path, jev_same_work_threshold=0.9)
    _use_http(monkeypatch, _FakeHttp(_noul(0.8)))

    assert (await evaluate_candidate(SOURCE_TITLE, 2025, "movie", CANDIDATE)).verdict is GateVerdict.REJECT


def test_gate_threshold_is_read_from_config_file(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """阈值来自配置文件而非代码常量：改配置即生效（§9 标定可无发版回退/上调）。"""
    store = _use_config(monkeypatch, tmp_path, jev_same_work_threshold=0.62)
    assert decision_client.load_gate_config().threshold == 0.62

    store.save_config({"jev_same_work_threshold": 0.88})
    assert decision_client.load_gate_config().threshold == 0.88


# ── 降级：JEV 不可用一律回退旧启发式 ─────────────────────────


async def test_http_error_falls_back_to_heuristic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, _fast_retry: None
) -> None:
    """HTTP 错误 → 回退启发式（不改变下单行为）+ 计数。"""
    _use_config(monkeypatch, tmp_path)
    fake = _use_http(monkeypatch, _FakeHttp({"error": "HTTP 500", "detail": "boom"}))

    result = await evaluate_candidate(SOURCE_TITLE, 2025, "movie", CANDIDATE)

    assert result.verdict is GateVerdict.FALLBACK
    assert len(fake.calls) == decision_client._MAX_ATTEMPTS  # 整体重试 3 次
    assert get_gate_metrics()["fallbacks"] == 1


async def test_timeout_falls_back_to_heuristic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, _fast_retry: None
) -> None:
    """超时 → 回退启发式。"""
    _use_config(monkeypatch, tmp_path)
    _use_http(monkeypatch, _FakeHttp(error=TimeoutError()))

    result = await evaluate_candidate(SOURCE_TITLE, 2025, "movie", CANDIDATE)

    assert result.verdict is GateVerdict.FALLBACK
    assert "超时" in result.reason


async def test_missing_field_falls_back_to_heuristic(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """响应缺少 same_work 字段 → 按降级处理，不得当成拒绝。"""
    _use_config(monkeypatch, tmp_path)
    _use_http(monkeypatch, _FakeHttp({"model": "jev-1.13.0", "answers": {}}))

    result = await evaluate_candidate(SOURCE_TITLE, 2025, "movie", CANDIDATE)

    assert result.verdict is GateVerdict.FALLBACK
    assert "same_work__0" in result.reason


async def test_missing_api_key_degrades_without_calling(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """没配密钥 → 可见降级（error 日志 + 计数），不发请求。"""
    monkeypatch.delenv(decision_client._ENV_API_KEY, raising=False)
    _use_config(monkeypatch, tmp_path, jev_api_key="")
    fake = _use_http(monkeypatch, _FakeHttp(_noul(0.9)))

    result = await evaluate_candidate(SOURCE_TITLE, 2025, "movie", CANDIDATE)

    assert result.verdict is GateVerdict.FALLBACK
    assert fake.calls == []
    assert get_gate_metrics()["fallbacks"] == 1


async def test_degradation_is_logged_as_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    caplog: pytest.LogCaptureFixture,
    _fast_retry: None,
) -> None:
    """降级必须可见：error 级日志含「JEV 不可用，回退启发式」。"""
    _use_config(monkeypatch, tmp_path)
    _use_http(monkeypatch, _FakeHttp(error=TimeoutError()))

    with caplog.at_level("ERROR"):
        await evaluate_candidate(SOURCE_TITLE, 2025, "movie", CANDIDATE)

    assert any("JEV 不可用，回退启发式" in record.getMessage() for record in caplog.records)


# ── 熔断 ────────────────────────────────────────────────────


async def test_breaker_opens_after_consecutive_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, _fast_retry: None
) -> None:
    """连续失败达阈值后熔断，冷却期内不再发请求（避免整轮任务被拖垮）。"""
    _use_config(monkeypatch, tmp_path)
    fake = _use_http(monkeypatch, _FakeHttp(error=TimeoutError()))

    for _ in range(decision._BREAKER_THRESHOLD):
        assert (await evaluate_candidate(SOURCE_TITLE, 2025, "movie", CANDIDATE)).verdict is GateVerdict.FALLBACK

    assert get_gate_metrics()["breaker_open"] is True
    calls_before = len(fake.calls)
    await evaluate_candidate(SOURCE_TITLE, 2025, "movie", CANDIDATE)
    assert len(fake.calls) == calls_before  # 熔断期间不发起调用


async def test_success_resets_failure_streak(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, _fast_retry: None
) -> None:
    """一次成功即复位连续失败计数（熔断半开恢复）。"""
    _use_config(monkeypatch, tmp_path)
    fake = _use_http(monkeypatch, _FakeHttp(error=TimeoutError()))
    await evaluate_candidate(SOURCE_TITLE, 2025, "movie", CANDIDATE)
    assert get_gate_metrics()["consecutive_failures"] == 1

    fake.error = None
    fake.response = _noul(0.9)
    await evaluate_candidate(SOURCE_TITLE, 2025, "movie", CANDIDATE)
    assert get_gate_metrics()["consecutive_failures"] == 0


# ── 红线 ────────────────────────────────────────────────────


async def test_model_alias_is_replaced_by_pinned_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """红线：别名 jev-latest 不得生效，自动回退到 pin 版本。"""
    _use_config(monkeypatch, tmp_path, jev_model="jev-latest")
    fake = _use_http(monkeypatch, _FakeHttp(_noul(0.9)))

    await evaluate_candidate(SOURCE_TITLE, 2025, "movie", CANDIDATE)

    assert fake.calls[0][2]["model"] == decision_client.PINNED_MODEL


def test_decision_module_has_no_bare_http_libs() -> None:
    """红线：闸门只能走 core/http_client，禁裸 urllib/requests/httpx/aiohttp。"""
    banned = {"httpx", "requests", "urllib", "aiohttp"}
    for module in (decision, decision_client):
        imported = _imported_modules(module)
        assert not {name for name in imported if name.split(".")[0] in banned}, module.__name__
    assert "app.core.http_client" in _imported_modules(decision_client)
    assert "app.services.decision_client" in _imported_modules(decision)


def _imported_modules(module: Any) -> set[str]:
    """收集模块源码里 import 的全部模块名。"""
    tree = ast.parse(pathlib.Path(module.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_attached_request_strategy_keeps_shared_script_policy() -> None:
    """请求策略与共享脚本一致：重试 3 次、单次 8s、总预算 10s。"""
    assert decision_client._MAX_ATTEMPTS == 3
    assert decision_client._ATTEMPT_TIMEOUT_S == 8.0
    assert decision_client._TOTAL_BUDGET_S == 10.0
    assert decision_client._BACKOFF_S == (1.0, 2.0)


# ── 与匹配流水线的接入（阶段 1~3 免闸门，阶段 4/5 才复核） ──


async def test_exact_match_never_calls_jev(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """精确匹配免费零延迟，不得花 JEV 的钱。"""
    _use_config(monkeypatch, tmp_path)
    fake = _use_http(monkeypatch, _FakeHttp(_noul(0.01)))
    results = [{"title": "深海幽灵", "year": 2025, "raw_type": "movie", "vote_average": 6.0}]

    picked = await matching.pick_best_gated(results, "深海幽灵", "movie", "2025")

    assert picked is not None
    assert fake.calls == []


async def test_fallback_candidate_is_vetoed_by_gate(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """阶段 5 兜底候选被闸门拒绝 → 返回 None（上层走未识别）。"""
    _use_config(monkeypatch, tmp_path)
    _use_http(monkeypatch, _FakeHttp(_noul(0.2)))

    picked = await matching.pick_best_gated([CANDIDATE], SOURCE_TITLE, "movie", "2025")

    assert picked is None
    assert get_gate_metrics()["rejected"] == 1


async def test_fallback_candidate_kept_when_gate_passes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """闸门放行时保留启发式结果。"""
    _use_config(monkeypatch, tmp_path)
    _use_http(monkeypatch, _FakeHttp(_noul(0.99)))

    assert await matching.pick_best_gated([CANDIDATE], SOURCE_TITLE, "movie", "2025") == CANDIDATE


async def test_gate_disabled_keeps_previous_behaviour(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """闸门关闭时行为与改动前完全一致（走原兜底逻辑）。"""
    _use_config(monkeypatch, tmp_path, jev_decision_enabled=False)
    fake = _use_http(monkeypatch, _FakeHttp(_noul(0.0)))

    assert await matching.pick_best_gated([CANDIDATE], SOURCE_TITLE, "movie", "2025") == CANDIDATE
    assert matching.pick_best([CANDIDATE], SOURCE_TITLE, "movie", "2025") == CANDIDATE
    assert fake.calls == []
