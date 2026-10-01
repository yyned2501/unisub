"""基础 API 测试 — 健康检查与根路径。

注意：client 夹具统一由 conftest 提供（已覆盖 get_db），本文件不再自带夹具。
自带版本会绕过依赖覆盖，使 /health 直接使用 app.core.database 的真实引擎。
"""


async def test_root(client):
    """根路径返回服务信息。"""
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "UniSub Backend"
    assert data["status"] == "running"


async def test_health(client):
    """健康检查端点可达（DB 探测走被覆盖的测试会话，不触生产库）。"""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("healthy", "degraded")


async def test_protected_endpoint_requires_auth(client):
    """未认证访问业务端点应返回 401/403。"""
    resp = await client.get("/api/subscriptions")
    assert resp.status_code in (401, 403)
