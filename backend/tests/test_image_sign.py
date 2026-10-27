"""Emby 图片代理签名测试 — HMAC 签发/校验与代理端点行为。"""

from urllib.parse import parse_qs, urlparse

from httpx import AsyncClient

from app.core.image_sign import sign_emby_image_path, verify_emby_image_sig
from app.main import app
from app.services import require_emby_service
from app.services.emby.service import EmbyService


def _parse(path: str) -> tuple[str, int, str]:
    """从签名路径中拆出 emby_id、exp、sig。"""
    parts = urlparse(path)
    emby_id = parts.path.rsplit("/", 1)[-1]
    query = parse_qs(parts.query)
    return emby_id, int(query["exp"][0]), query["sig"][0]


def test_sign_and_verify_roundtrip():
    """签发的路径应能通过校验，前缀与参数齐全。"""
    path = sign_emby_image_path("abc123")
    assert path.startswith("/api/emby/image/abc123?")
    emby_id, exp, sig = _parse(path)
    assert verify_emby_image_sig(emby_id, exp, sig)


def test_verify_rejects_tampered_sig():
    """篡改签名或 emby_id 都应校验失败。"""
    path = sign_emby_image_path("abc123")
    emby_id, exp, sig = _parse(path)
    tampered = sig[:-1] + ("0" if sig[-1] != "0" else "1")
    assert not verify_emby_image_sig(emby_id, exp, tampered)
    assert not verify_emby_image_sig("other-id", exp, sig)


def test_verify_rejects_expired():
    """过期签名（ttl 为负）应校验失败。"""
    path = sign_emby_image_path("abc123", ttl=-10)
    emby_id, exp, sig = _parse(path)
    assert not verify_emby_image_sig(emby_id, exp, sig)


async def test_proxy_endpoint_rejects_bad_sig(client: AsyncClient):
    """签名无效时代理端点返回 403（本端点无需 JWT 头）。"""
    app.dependency_overrides[require_emby_service] = lambda: EmbyService("http://emby.test", "test-key")
    resp = await client.get("/api/emby/image/abc123", params={"exp": 9999999999, "sig": "deadbeef"})
    assert resp.status_code == 403


async def test_proxy_endpoint_streams_image(client: AsyncClient, monkeypatch):
    """有效签名 → 用 X-Emby-Token 头取图并原样返回字节与 Content-Type。"""
    import app.services.emby.service as emby_module

    async def fake_get_bytes(url, headers=None):
        assert url == "http://emby.test/Items/abc123/Images/Primary"
        assert headers == {"X-Emby-Token": "test-key"}
        return b"fake-image-bytes", "image/jpeg"

    monkeypatch.setattr(emby_module.http_client, "get_bytes", fake_get_bytes)
    app.dependency_overrides[require_emby_service] = lambda: EmbyService("http://emby.test", "test-key")

    path = sign_emby_image_path("abc123")
    emby_id, exp, sig = _parse(path)
    resp = await client.get(f"/api/emby/image/{emby_id}", params={"exp": exp, "sig": sig})
    assert resp.status_code == 200
    assert resp.content == b"fake-image-bytes"
    assert resp.headers["Content-Type"].startswith("image/jpeg")
