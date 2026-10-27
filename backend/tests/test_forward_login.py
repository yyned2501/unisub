"""Forward 登录 fail-closed 回归测试。

历史缺陷：账号配置为空（``{}``）时，空用户名 / 空密码的表单提交会命中
「空 == 空」比较并签发 JWT —— 未鉴权即可拿到管理 token。
"""

import pytest

from app.core import login_guard
from app.routers import forward as forward_router
from app.services import forward as forward_service
from app.services.forward import ForwardService

LOGIN_URL = "/api/v1/login/access-token"


@pytest.fixture(autouse=True)
def _clean_guard():
    """每个用例前后清空登录限流状态。"""
    login_guard.reset_all()
    yield
    login_guard.reset_all()


@pytest.fixture
def svc() -> ForwardService:
    """登录路径不触碰 NF / 编排层，用 None 构造即可。"""
    return ForwardService(None, None)  # type: ignore[arg-type]


def _stub_auth(monkeypatch, auth: dict) -> None:
    """固定账号配置来源，避免读到本机真实凭据。"""
    monkeypatch.setattr(forward_service, "load_auth_config", lambda: auth)


async def test_empty_config_rejects_empty_credentials(svc, monkeypatch):
    """空账号配置 + 空表单不得放行（原越权路径）。"""
    _stub_auth(monkeypatch, {})
    result = await svc.login("", "", "", "")
    assert result["success"] is False
    assert "access_token" not in result


async def test_empty_config_rejects_any_credentials(svc, monkeypatch):
    """空账号配置时任何凭据都不得放行。"""
    _stub_auth(monkeypatch, {})
    result = await svc.login("admin", "password", "", "")
    assert result["success"] is False


@pytest.mark.parametrize(
    ("username", "password"),
    [("", ""), ("admin", ""), ("", "s3cret")],
)
async def test_blank_submission_rejected_when_configured(svc, monkeypatch, username, password):
    """已配置凭据时，空字段提交一律拒绝。"""
    _stub_auth(monkeypatch, {"username": "admin", "password": "s3cret"})
    result = await svc.login(username, password, "admin", "s3cret")
    assert result["success"] is False


async def test_wrong_credentials_rejected(svc, monkeypatch):
    """密码错误时拒绝且不签发 token。"""
    _stub_auth(monkeypatch, {"username": "admin", "password": "s3cret"})
    result = await svc.login("admin", "wrong", "admin", "s3cret")
    assert result["success"] is False
    assert "access_token" not in result


async def test_correct_credentials_issue_token(svc, monkeypatch):
    """正确凭据签发 token（避免改成了「永远拒绝」）。"""
    _stub_auth(monkeypatch, {"username": "admin", "password": "s3cret"})
    result = await svc.login("admin", "s3cret", "admin", "s3cret")
    assert result["access_token"]
    assert result["user_name"] == "admin"


async def test_endpoint_returns_401_when_config_missing(client, monkeypatch):
    """端到端：服务端未配置账号时，任何提交都返回 401 且不泄露 token。

    空字符串会被 FastAPI 表单校验拦成 422，因此这里用空白字符验证服务端的
    配置侧拦截（fail-closed 的最后一道闸）。
    """

    async def _fake_get_service(db):
        return ForwardService(None, None)  # type: ignore[arg-type]

    monkeypatch.setattr(forward_router, "_get_forward_service", _fake_get_service)
    monkeypatch.setattr(forward_router, "load_auth_config", lambda: {})
    _stub_auth(monkeypatch, {})

    resp = await client.post(LOGIN_URL, data={"username": " ", "password": " "})
    assert resp.status_code == 401, resp.text
    assert "access_token" not in resp.text
