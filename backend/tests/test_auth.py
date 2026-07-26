"""JWT 认证模块测试 — Token 签发、验证与依赖注入。"""

import pytest
from fastapi import HTTPException

from app.core.auth import create_access_token, verify_token


def test_create_access_token_returns_string():
    """create_access_token 应返回非空字符串。"""
    token = create_access_token("alice")
    assert isinstance(token, str)
    assert len(token) > 0


async def test_verify_token_valid():
    """有效 token 应成功解析出用户名。"""
    token = create_access_token("bob")
    payload = await verify_token(token)
    assert payload["sub"] == "bob"
    assert "exp" in payload
    assert "iat" in payload


async def test_verify_token_invalid():
    """无效 token 应抛出 401 HTTPException。"""
    with pytest.raises(HTTPException) as exc_info:
        await verify_token("invalid.token.here")
    assert exc_info.value.status_code == 401


async def test_verify_token_tampered():
    """篡改的 token 应验证失败。"""
    token = create_access_token("charlie")
    tampered = token[:-5] + "XXXXX"
    with pytest.raises(HTTPException) as exc_info:
        await verify_token(tampered)
    assert exc_info.value.status_code == 401


def test_create_token_different_users():
    """不同用户应生成不同 token。"""
    t1 = create_access_token("user1")
    t2 = create_access_token("user2")
    assert t1 != t2
