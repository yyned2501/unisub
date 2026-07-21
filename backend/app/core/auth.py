"""JWT 认证模块 — Token 签发与验证。

提供本地 JWT 签发/验证，用于 Forward API 的登录认证。
"""

from datetime import UTC, datetime, timedelta

import jwt
from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer

from app.config import parse_config

config = parse_config()

SECRET_KEY = config.jwt_secret
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 天

_scheme = HTTPBearer(auto_error=False)


def create_access_token(username: str) -> str:
    """创建 JWT access token。

    Args:
        username: 用户名

    Returns:
        JWT 字符串
    """
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": username,
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def verify_token(token: str) -> dict:
    """验证 JWT token，返回 payload。

    Args:
        token: JWT 字符串

    Returns:
        token payload 字典

    Raises:
        HTTPException: token 无效或已过期
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的 Token")


async def get_current_user(request: Request) -> str:
    """FastAPI 依赖注入 — 从 Authorization header 解析当前用户名。

    在路由中通过 Depends(get_current_user) 使用。

    Args:
        request: FastAPI 请求对象

    Returns:
        用户名

    Raises:
        HTTPException: 未提供或无效的 token
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="未提供认证信息")

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authorization 格式错误，使用 Bearer <token>")

    payload = await verify_token(parts[1])
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Token payload 无效")
    return username
