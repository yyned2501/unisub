"""基础 API 测试 — 健康检查与根路径。"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    """异步测试客户端。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_root(client):
    """根路径返回服务信息。"""
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "UniSub Backend"
    assert data["status"] == "running"


async def test_health(client):
    """健康检查端点可达。"""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("healthy", "degraded")


async def test_protected_endpoint_requires_auth(client):
    """未认证访问业务端点应返回 401/403。"""
    resp = await client.get("/api/subscriptions")
    assert resp.status_code in (401, 403)
