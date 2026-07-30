"""AI 配置 API 测试。"""

from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient


async def test_ai_config_requires_auth(client: AsyncClient) -> None:
    """未认证请求 AI 配置应被拒绝。"""
    response = await client.get("/api/ai/config")

    assert response.status_code == 401


async def test_ai_config_api_round_trip(
    client: AsyncClient, auth_headers: dict[str, str], tmp_path: Path, monkeypatch
) -> None:
    """AI 配置接口应读写独立配置而不影响自动订阅配置。"""
    from app.routers import ai
    from app.services.ai_config import AiConfigStore

    store = AiConfigStore(config_path=tmp_path / "ai_config.json", legacy_config_path=tmp_path / "legacy.json")
    monkeypatch.setattr(ai, "get_ai_config_store", lambda: store)

    response = await client.put(
        "/api/ai/config",
        headers=auth_headers,
        json={"config": {"ai_assist_enabled": True, "ai_model": "test-model"}},
    )

    assert response.status_code == 200
    assert response.json()["config"]["ai_assist_enabled"] is True
    assert response.json()["config"]["ai_model"] == "test-model"

    response = await client.get("/api/ai/config", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["config"]["ai_model"] == "test-model"
