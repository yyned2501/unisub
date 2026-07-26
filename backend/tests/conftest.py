"""测试夹具 — 提供异步数据库会话和 FastAPI 测试客户端。

使用 aiosqlite 内存数据库，无需外部 PostgreSQL 即可运行测试。
"""

import os

# 在导入 app 之前设置测试环境变量，避免连接真实数据库
os.environ.setdefault("UNISUB_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("UNISUB_JWT_SECRET", "test-secret-key-that-is-long-enough-32b")
os.environ.setdefault("UNISUB_DEBUG", "false")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app

# 测试用内存数据库引擎
_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_test_session_factory = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def setup_database():
    """每个测试前创建表，测试后清理。"""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session() -> AsyncSession:
    """提供独立的测试数据库会话。"""
    async with _test_session_factory() as session:
        yield session


@pytest.fixture
async def client(db_session: AsyncSession):
    """提供 FastAPI 测试客户端，覆盖数据库依赖。"""

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """生成有效的 JWT 认证头。"""
    from app.core.auth import create_access_token

    token = create_access_token("testuser")
    return {"Authorization": f"Bearer {token}"}
