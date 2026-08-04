"""数据库模块 — SQLAlchemy async 引擎、会话工厂与表创建。"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import parse_config

config = parse_config()

# pool_pre_ping: 取连接前先探活，避免夜间闲置连接被服务端掐断后整轮同步失败
# pool_recycle: 连接存活 30 分钟即回收重建，规避 NAS/防火墙的闲置断连
engine = create_async_engine(
    config.database_url,
    echo=config.debug,
    pool_pre_ping=True,
    pool_recycle=1800,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类，所有 ORM 模型继承自此。"""

    pass


async def get_db():
    """FastAPI 依赖注入 — 为每个请求生成数据库会话。

    用法:
        @router.get("/")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """创建所有数据库表（开发阶段使用，生产环境应使用 Alembic 迁移）。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
