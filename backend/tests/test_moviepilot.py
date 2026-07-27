"""MoviePilot 服务测试 — 订阅相关接口的请求构造与响应解析。

用 monkeypatch 替换 http_client 的方法，不发起真实网络请求。
"""

import app.services.moviepilot as mp_module
from app.services.moviepilot import MoviePilotService


def _make_service() -> MoviePilotService:
    """构造测试用 MoviePilot 服务实例。"""
    return MoviePilotService("http://mp.test:3000", "test-token")


async def test_create_subscription_tv_body(monkeypatch):
    """电视剧创建订阅应透传 tmdbid/type/season，不含只读运行字段。"""
    captured: dict = {}

    async def fake_post(url, headers=None, json=None, data=None):
        captured["url"] = url
        captured["json"] = json
        return {"success": True, "data": {"id": 42}}

    monkeypatch.setattr(mp_module.http_client, "post", fake_post)
    svc = _make_service()
    result = await svc.create_subscription(123, "tv", "测试剧", year=2024, season=2)

    assert result["data"]["id"] == 42
    assert captured["url"].endswith("/api/v1/subscribe/")
    body = captured["json"]
    assert body["tmdbid"] == 123
    # type 必须映射成 MP 认的中文值，英文 tv 会触发 MP 端 500
    assert body["type"] == "电视剧"
    assert body["season"] == 2
    assert body["year"] == "2024"
    assert body["name"] == "测试剧"
    # 媒体身份字段需透传
    assert body["media_source"] == "themoviedb"
    assert body["media_id"] == "123"
    # 只读运行字段不得出现在请求体
    for forbidden in ("state", "lack_episode", "date", "id"):
        assert forbidden not in body


async def test_create_subscription_movie_no_season(monkeypatch):
    """电影创建订阅不应带 season 字段。"""
    captured: dict = {}

    async def fake_post(url, headers=None, json=None, data=None):
        captured["json"] = json
        return {"success": True, "data": {"id": 7}}

    monkeypatch.setattr(mp_module.http_client, "post", fake_post)
    svc = _make_service()
    await svc.create_subscription(555, "movie", "测试电影")

    assert "season" not in captured["json"]
    assert captured["json"]["type"] == "电影"


async def test_create_subscription_error_passthrough(monkeypatch):
    """创建订阅失败应原样返回 error 字典。"""

    async def fake_post(url, headers=None, json=None, data=None):
        return {"error": "HTTP 500", "detail": "boom"}

    monkeypatch.setattr(mp_module.http_client, "post", fake_post)
    svc = _make_service()
    result = await svc.create_subscription(1, "tv", "x", season=1)
    assert "error" in result


async def test_get_missing_seasons_parses_list(monkeypatch):
    """notexists 返回缺集季列表应原样透传。"""
    payload = [
        {"season": 1, "episodes": [3, 4], "total_episode": 10},
        {"season": 2, "episodes": [1], "total_episode": 8},
    ]

    async def fake_post(url, headers=None, json=None, data=None):
        assert url.endswith("/api/v1/mediaserver/notexists")
        return payload

    monkeypatch.setattr(mp_module.http_client, "post", fake_post)
    svc = _make_service()
    result = await svc.get_missing_seasons(123, "tv", "测试剧")
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["season"] == 1


async def test_get_missing_seasons_error_returns_dict(monkeypatch):
    """notexists 失败应返回含 error 的字典（调用方据此降级）。"""

    async def fake_post(url, headers=None, json=None, data=None):
        return {"error": "HTTP 500", "detail": "media server down"}

    monkeypatch.setattr(mp_module.http_client, "post", fake_post)
    svc = _make_service()
    result = await svc.get_missing_seasons(123, "tv", "x")
    assert isinstance(result, dict)
    assert "error" in result


async def test_get_missing_seasons_uses_chinese_type(monkeypatch):
    """notexists 的 type 必须映射成中文（电视剧），英文会触发 MP 端 500。"""
    captured: dict = {}

    async def fake_post(url, headers=None, json=None, data=None):
        captured["json"] = json
        return []

    monkeypatch.setattr(mp_module.http_client, "post", fake_post)
    svc = _make_service()
    await svc.get_missing_seasons(37854, "tv", "航海王", year=1999)
    assert captured["json"]["type"] == "电视剧"
    assert captured["json"]["media_source"] == "themoviedb"
    assert captured["json"]["media_id"] == "37854"


def test_auth_header_is_x_api_key():
    """鉴权必须用 X-API-Key 头；Authorization: Bearer 会被 MP 拒绝（403）。"""
    svc = _make_service()
    assert svc._headers.get("X-API-Key") == "test-token"
    assert "Authorization" not in svc._headers


async def test_delete_subscription_uses_delete(monkeypatch):
    """删除订阅应调用 DELETE /api/v1/subscribe/{id}。"""
    captured: dict = {}

    async def fake_delete(url, headers=None):
        captured["url"] = url
        return {}

    monkeypatch.setattr(mp_module.http_client, "delete", fake_delete)
    svc = _make_service()
    await svc.delete_subscription(99)
    assert captured["url"].endswith("/api/v1/subscribe/99")


async def test_find_subscription_not_found(monkeypatch):
    """按媒体 ID 查询订阅不存在（error）应返回 None。"""

    async def fake_get(url, headers=None, params=None):
        return {"error": "HTTP 404", "detail": "not found"}

    monkeypatch.setattr(mp_module.http_client, "get", fake_get)
    svc = _make_service()
    assert await svc.find_subscription(123, season=1) is None


async def test_find_subscription_with_season_param(monkeypatch):
    """查询指定季时应带 season 查询参数。"""
    captured: dict = {}

    async def fake_get(url, headers=None, params=None):
        captured["url"] = url
        captured["params"] = params
        return {"id": 3}

    monkeypatch.setattr(mp_module.http_client, "get", fake_get)
    svc = _make_service()
    result = await svc.find_subscription(123, season=2)
    assert result == {"id": 3}
    assert captured["url"].endswith("/api/v1/subscribe/media/tmdb:123")
    assert captured["params"] == {"season": 2}
