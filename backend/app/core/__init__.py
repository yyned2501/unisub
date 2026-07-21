"""核心层 — 第三方库封装。

唯一可直接 import 第三方库（sqlalchemy、httpx 等）的层。
"""

from app.core.auth import create_access_token, get_current_user, verify_token
from app.core.database import Base, async_session, get_db, init_db
from app.core.http_client import AsyncHttpClient, http_client
from app.core.logger import init_logger

__all__ = [
    "AsyncHttpClient",
    "Base",
    "async_session",
    "create_access_token",
    "get_current_user",
    "get_db",
    "http_client",
    "init_db",
    "init_logger",
    "verify_token",
]
