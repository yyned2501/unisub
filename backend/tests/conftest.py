"""测试夹具 — 提供异步数据库会话和 FastAPI 测试客户端。

使用 aiosqlite 内存数据库，无需外部 PostgreSQL 即可运行测试。
"""

import os

# 在导入 app 之前设置测试环境变量，避免连接真实数据库。
# ⚠️ 必须硬赋值，不能用 setdefault：验收命令会先 `source backend/.env` 再跑 pytest，
# 此时 setdefault 会让真实 UNISUB_DATABASE_URL 穿透进来，app.core.database 在导入期
# 就绑定生产 PostgreSQL（/health 等直接用 async_session 的路径会真的打到生产库）。
os.environ["UNISUB_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["UNISUB_JWT_SECRET"] = "test-secret-key-that-is-long-enough-32b"
os.environ["UNISUB_DEBUG"] = "false"

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.logger import init_logger
from app.main import app

# 测试与生产共写 backend/logs/unisub.log，移除文件 handler 避免测试噪音污染生产日志
_test_logger = init_logger()
_test_logger.handlers = [h for h in _test_logger.handlers if h.__class__.__name__ == "StreamHandler"]

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
    """提供 FastAPI 测试客户端，覆盖数据库依赖。

    覆盖 get_db 后，所有走 Depends(get_db) 的端点都落到内存测试库，
    不再触碰生产 PostgreSQL。
    """

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def session_factory():
    """与 db_session 同一内存库的会话工厂 — 供后台任务注入使用。"""
    return _test_session_factory


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """生成有效的 JWT 认证头。"""
    from app.core.auth import create_access_token

    token = create_access_token("testuser")
    return {"Authorization": f"Bearer {token}"}
