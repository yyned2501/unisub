"""登录限流测试 — 失败计数、指数退避锁定、成功后清零。

覆盖两层：
1. ``app.core.login_guard`` 的纯逻辑（阈值 / 滑动窗口 / 退避 / 复位）
2. ``POST /api/v1/login/access-token`` 的接线（401 累计 → 429 锁定 → 成功清零）
"""

import pytest
from starlette.requests import Request

from app.core import login_guard
from app.routers import forward as forward_router

LOGIN_URL = "/api/v1/login/access-token"
USERNAME = "admin"
WRONG_FORM = {"username": USERNAME, "password": "wrong-password"}


class _StubForwardService:
    """只实现 login 的 ForwardService 替身，避免真连 NextFind。"""

    def __init__(self, success: bool) -> None:
        self._success = success

    async def login(self, username, password, config_username="", config_password=""):
        """返回预置的登录结果。"""
        if self._success:
            return {"success": True, "access_token": "stub-token", "token_type": "bearer"}
        return {"success": False, "message": "用户名或密码错误"}


@pytest.fixture(autouse=True)
def _clean_guard():
    """每个用例前后清空限流状态，避免跨用例串味。"""
    login_guard.reset_all()
    yield
    login_guard.reset_all()


@pytest.fixture(autouse=True)
def _env_auth(monkeypatch):
    """让 load_auth_config 走环境变量，不读（也不写）明文账号文件。"""
    monkeypatch.setenv("UNISUB_FORWARD_USERNAME", "admin")
    monkeypatch.setenv("UNISUB_FORWARD_PASSWORD", "test-password")


@pytest.fixture
def stub_login(monkeypatch):
    """安装 ForwardService 替身；调用 stub_login(True/False) 切换登录结果。"""

    def _install(success: bool) -> None:
        async def _fake_get_service(db):
            return _StubForwardService(success)

        monkeypatch.setattr(forward_router, "_get_forward_service", _fake_get_service)

    return _install


# ---------- 纯逻辑 ----------


def test_not_locked_initially():
    """未记录失败前不得锁定。"""
    assert login_guard.is_locked("1.1.1.1|admin") == (False, 0)


def test_locks_only_after_threshold():
    """达到阈值才锁定，阈值前只计数。"""
    key = "1.1.1.1|admin"
    for _ in range(login_guard.MAX_FAILURES - 1):
        login_guard.record_failure(key)
    assert login_guard.is_locked(key)[0] is False

    login_guard.record_failure(key)
    locked, remaining = login_guard.is_locked(key)
    assert locked is True
    assert 0 < remaining <= login_guard.BASE_LOCK_SECONDS + 1


def test_lock_duration_escalates_and_caps():
    """连续触发锁定时长翻倍，且不超过上限。"""
    key = "1.1.1.1|admin"
    durations = []
    for _ in range(4):
        for _ in range(login_guard.MAX_FAILURES):
            login_guard.record_failure(key)
        durations.append(login_guard.is_locked(key)[1])

    assert durations[0] <= login_guard.BASE_LOCK_SECONDS + 1
    assert durations[1] > durations[0]
    assert durations[2] > durations[1]
    assert durations[3] <= login_guard.MAX_LOCK_SECONDS + 1


def test_failures_outside_window_are_dropped(monkeypatch):
    """窗口外的失败不计入阈值，避免低频失败被永久累加。"""
    now = [1000.0]
    monkeypatch.setattr(login_guard, "_now", lambda: now[0])
    key = "1.1.1.1|admin"

    for _ in range(login_guard.MAX_FAILURES - 1):
        login_guard.record_failure(key)

    now[0] += login_guard.FAILURE_WINDOW + 1
    login_guard.record_failure(key)
    assert login_guard.is_locked(key)[0] is False


def test_reset_clears_state():
    """reset 后计数与锁定级别一并清零。"""
    key = "1.1.1.1|admin"
    for _ in range(login_guard.MAX_FAILURES):
        login_guard.record_failure(key)
    assert login_guard.is_locked(key)[0] is True

    login_guard.reset(key)
    assert login_guard.is_locked(key) == (False, 0)


def test_lock_key_normalizes_username():
    """限流键抹平大小写与首尾空格，防止换写法绕过计数。"""
    request = Request({"type": "http", "client": ("9.9.9.9", 1234)})
    assert forward_router._login_lock_key(request, "  Admin ") == "9.9.9.9|admin"


# ---------- 端点接线 ----------


async def test_login_locks_after_repeated_failures(client, stub_login):
    """连续失败达阈值后，端点返回 429 且带 Retry-After。"""
    stub_login(False)

    for attempt in range(1, login_guard.MAX_FAILURES + 1):
        resp = await client.post(LOGIN_URL, data=WRONG_FORM)
        assert resp.status_code == 401, f"第 {attempt} 次失败应为 401"

    resp = await client.post(LOGIN_URL, data=WRONG_FORM)
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) > 0


async def test_locked_request_skips_credential_check(client, stub_login):
    """锁定期间即使密码正确也不放行（先拦后校验）。"""
    stub_login(True)
    key = "127.0.0.1|admin"
    for _ in range(login_guard.MAX_FAILURES):
        login_guard.record_failure(key)

    resp = await client.post(LOGIN_URL, data={"username": USERNAME, "password": "test-password"})
    assert resp.status_code == 429


async def test_login_success_resets_failure_count(client, stub_login):
    """一次成功后计数清零，后续零散失败不会触发锁定。"""
    stub_login(False)
    for _ in range(login_guard.MAX_FAILURES - 1):
        resp = await client.post(LOGIN_URL, data=WRONG_FORM)
        assert resp.status_code == 401

    stub_login(True)
    resp = await client.post(LOGIN_URL, data={"username": USERNAME, "password": "test-password"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    stub_login(False)
    for _ in range(login_guard.MAX_FAILURES - 1):
        resp = await client.post(LOGIN_URL, data=WRONG_FORM)
        assert resp.status_code == 401, "计数未清零：应当重新从 0 累计"
