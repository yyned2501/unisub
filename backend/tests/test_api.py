"""API 端点测试 — 健康检查、认证保护与订阅 CRUD。"""

from httpx import AsyncClient


async def test_root_health(client: AsyncClient):
    """根路径应返回服务状态。"""
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "UniSub Backend"
    assert data["status"] == "running"


async def test_health_endpoint(client: AsyncClient):
    """/health 应返回数据库连通状态。"""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("healthy", "degraded")


async def test_subscriptions_requires_auth(client: AsyncClient):
    """未认证访问订阅列表应返回 401。"""
    resp = await client.get("/api/subscriptions")
    assert resp.status_code == 401


async def test_subscriptions_list_empty(client: AsyncClient, auth_headers: dict[str, str]):
    """认证后访问空订阅列表应返回空数组。"""
    resp = await client.get("/api/subscriptions", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_dashboard_requires_auth(client: AsyncClient):
    """未认证访问看板应返回 401。"""
    resp = await client.get("/api/dashboard/stats")
    assert resp.status_code == 401


async def test_platforms_requires_auth(client: AsyncClient):
    """未认证访问平台列表应返回 401。"""
    resp = await client.get("/api/platforms")
    assert resp.status_code == 401
