"""MoviePilot 连接失败熔断测试 — 连续连接失败后暂停调用，成功即复位。"""

import app.services.moviepilot as mp_module
from app.services.moviepilot import MoviePilotService

_CONN_FAIL = {"error": "request_failed", "detail": "All connection attempts failed"}


def _make_service() -> MoviePilotService:
    """构造测试用 MoviePilot 服务实例。"""
    return MoviePilotService("http://mp.test:3000", "test-token")


async def test_breaker_opens_after_consecutive_conn_failures(monkeypatch):
    """连续连接失败达到阈值后熔断打开，不再发起真实请求。"""
    calls = {"n": 0}

    async def fake_get(url, headers=None, params=None):
        calls["n"] += 1
        return dict(_CONN_FAIL)

    monkeypatch.setattr(mp_module.http_client, "get", fake_get)
    svc = _make_service()

    for _ in range(mp_module._CONN_FAIL_THRESHOLD):
        await svc.get_subscription_detail(1)
    assert calls["n"] == mp_module._CONN_FAIL_THRESHOLD

    # 熔断打开后再调用：不产生真实请求，直接返回熔断错误
    result = await svc.get_subscription_detail(1)
    assert calls["n"] == mp_module._CONN_FAIL_THRESHOLD
    assert result["error"] == "request_failed"
    assert "熔断" in result["detail"]


async def test_breaker_resets_on_success(monkeypatch):
    """成功响应应复位失败计数，未连续达到阈值不触发熔断。"""
    calls = {"n": 0}

    async def fake_get(url, headers=None, params=None):
        calls["n"] += 1
        # 每 4 次失败后成功一次（阈值 5，始终不连续）
        return dict(_CONN_FAIL) if calls["n"] % 5 else {"id": 1, "state": "R"}

    monkeypatch.setattr(mp_module.http_client, "get", fake_get)
    svc = _make_service()

    for _ in range(12):
        await svc.get_subscription_detail(1)
    # 每次都发起了真实请求 → 熔断从未打开
    assert calls["n"] == 12


async def test_http_error_does_not_trigger_breaker(monkeypatch):
    """HTTP 状态码错误（服务存活）不计入连接失败。"""
    calls = {"n": 0}

    async def fake_get(url, headers=None, params=None):
        calls["n"] += 1
        return {"error": "HTTP 500", "detail": "boom"}

    monkeypatch.setattr(mp_module.http_client, "get", fake_get)
    svc = _make_service()

    for _ in range(mp_module._CONN_FAIL_THRESHOLD + 2):
        await svc.get_subscription_detail(1)
    assert calls["n"] == mp_module._CONN_FAIL_THRESHOLD + 2


async def test_breaker_half_open_after_cooldown(monkeypatch):
    """冷却期过后允许再次尝试（半开），成功则复位。"""
    calls = {"n": 0}

    async def fake_get(url, headers=None, params=None):
        calls["n"] += 1
        return dict(_CONN_FAIL) if calls["n"] <= mp_module._CONN_FAIL_THRESHOLD else {"id": 1}

    monkeypatch.setattr(mp_module.http_client, "get", fake_get)
    svc = _make_service()

    for _ in range(mp_module._CONN_FAIL_THRESHOLD):
        await svc.get_subscription_detail(1)
    # 模拟冷却期已过
    svc._breaker_until = 0.0

    result = await svc.get_subscription_detail(1)
    assert calls["n"] == mp_module._CONN_FAIL_THRESHOLD + 1
    assert result == {"id": 1}
    assert svc._conn_failures == 0
