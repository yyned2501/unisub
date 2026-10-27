"""JEV 采纳闸门 — 配置读取与 HTTP 调用（JEV 传输层唯一入口）。

请求策略沿用共享脚本 `~/.hermes/scripts/jev.py`：整体重试 3 次、退避 1s/2s、
单次超时 8s、总预算 10s。共享脚本的「IPv4 优先」由 httpx/OS 解析承担
（HTTP 必须走 `core/http_client.py`，不把共享脚本的裸 socket 逻辑搬进来）。
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any

from app.core.http_client import http_client
from app.core.logger import init_logger
from app.services.ai_config import get_ai_config_store

logger = init_logger()

# 密钥来源：ai_config.jev_api_key > 环境变量（backend/.env，gitignore）
_ENV_API_KEY = "UNISUB_JEV_API_KEY"

# 版本 pin：带 latest 的别名会漂移，阈值标定随之失效（红线）
PINNED_MODEL = "jev-1.13.0"
_ALIAS_SUFFIXES = ("latest",)

_DEFAULT_API_BASE = "https://api.typesafe.ai"
_ATTEMPT_TIMEOUT_S = 8.0
_TOTAL_BUDGET_S = 10.0
_MAX_ATTEMPTS = 3
_BACKOFF_S = (1.0, 2.0)


@dataclass(frozen=True)
class GateConfig:
    """闸门运行配置（来自 `ai_config`，便于无发版调整）。"""

    enabled: bool
    shadow: bool
    api_base: str
    api_key: str
    model: str
    threshold: float


def load_gate_config() -> GateConfig:
    """从 `ai_config` 读取闸门配置（密钥可回落环境变量，模型别名自动纠正）。"""
    raw = get_ai_config_store().load_config()
    api_key = str(raw.get("jev_api_key") or "").strip() or os.getenv(_ENV_API_KEY, "").strip()
    model = str(raw.get("jev_model") or "").strip() or PINNED_MODEL
    if model.endswith(_ALIAS_SUFFIXES):
        logger.error("JEV 模型 %s 是 latest 别名，已回退到 pin 版本 %s（别名漂移会使阈值失效）", model, PINNED_MODEL)
        model = PINNED_MODEL
    return GateConfig(
        enabled=bool(raw.get("jev_decision_enabled")),
        shadow=bool(raw.get("jev_decision_shadow", True)),
        api_base=str(raw.get("jev_api_base") or "").strip() or _DEFAULT_API_BASE,
        api_key=api_key,
        model=model,
        threshold=_threshold(raw.get("jev_same_work_threshold")),
    )


async def call_jev(
    cfg: GateConfig,
    state: dict[str, Any],
    questions: dict[str, Any],
) -> tuple[dict | None, str | None, float]:
    """调用 JEV `/v1/systemone`（走 `core/http_client`），返回 (响应, 错误, 耗时)。

    超时/异常/HTTP 错误字典都只返回错误描述，由调用方统一降级 —— 单点失败不得影响主流程。
    """
    if not cfg.api_key:
        return None, f"未配置 JEV 密钥（ai_config.jev_api_key 或环境变量 {_ENV_API_KEY}）", 0.0

    url = f"{cfg.api_base.rstrip('/')}/v1/systemone"
    headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}
    body = {"model": cfg.model, "state": state, "questions": questions}
    deadline = time.monotonic() + _TOTAL_BUDGET_S
    started = time.monotonic()
    last_error = "未知错误"

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        remain = deadline - time.monotonic()
        if remain <= 0.5:
            last_error = f"总预算 {_TOTAL_BUDGET_S:.0f}s 已耗尽"
            break
        try:
            response = await asyncio.wait_for(
                http_client.post(url, headers=headers, json=body),
                timeout=min(_ATTEMPT_TIMEOUT_S, remain),
            )
        except TimeoutError:
            last_error = f"超时（第 {attempt}/{_MAX_ATTEMPTS} 次）"
        except Exception as exc:  # noqa: BLE001 — 任何异常都必须降级，闸门不能把整轮任务打崩
            last_error = f"{type(exc).__name__}: {exc}"
        else:
            if isinstance(response, dict) and "error" not in response:
                return response, None, time.monotonic() - started
            detail = response.get("error") if isinstance(response, dict) else "响应非 JSON 对象"
            last_error = f"HTTP 错误 {detail}"

        if attempt < _MAX_ATTEMPTS:
            wait = _BACKOFF_S[min(attempt - 1, len(_BACKOFF_S) - 1)]
            if time.monotonic() + wait < deadline:
                await asyncio.sleep(wait)

    return None, last_error, time.monotonic() - started


def extract_same_work(response: dict) -> float | None:
    """从响应里取 `answers.same_work__0.noul`；缺失或非数值返回 None（按降级处理）。"""
    answers = response.get("answers")
    if not isinstance(answers, dict):
        return None
    answer = answers.get("same_work__0")
    if not isinstance(answer, dict):
        return None
    value = answer.get("noul")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0.0, min(1.0, float(value)))


def _threshold(raw: Any) -> float:
    """解析阈值（非法值回落 0.75 —— `docs/SPEC-JEV-DECISION.md` §9 标定值）。"""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.75
    return value if 0.0 < value <= 1.0 else 0.75
