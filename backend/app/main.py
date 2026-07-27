"""UniSub 后端入口 — FastAPI 应用工厂。

负责:
    - 生命周期管理（启动初始化数据库、关闭清理 HTTP 客户端）
    - 注册所有路由
    - CORS 中间件
    - 全局异常处理
"""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.config import parse_config
from app.core.database import async_session, init_db
from app.core.http_client import http_client
from app.core.logger import init_logger
from app.models.platform_config import PlatformConfig
from app.routers import (
    auto_subscribe,
    cd2,
    dashboard,
    emby,
    forward,
    logs,
    platforms,
    search,
    subscriptions,
    tasks,
)

config = parse_config()
logger = init_logger(config.debug)


async def _seed_default_platforms():
    """启动时自动创建默认平台配置（如果不存在）。

    moviepilot 也在此 seed：MP 镜像订阅依赖 platform_configs 里的 moviepilot 记录，
    若不存在则 get_mp_service 返回 None、整条 MP 链路被跳过。seed 出占位卡片后，
    用户在平台设置页填入 base_url + api_key 即可启用。
    """
    defaults = [
        {
            "name": "tmdb",
            "base_url": "https://api.themoviedb.org/3",
            "api_key": "",
            "enabled": True,
        },
        {
            "name": "moviepilot",
            "base_url": "http://192.168.31.10:3000",
            "api_key": "",
            "enabled": False,
        },
    ]
    async with async_session() as session:
        for item in defaults:
            existing = await session.execute(select(PlatformConfig).where(PlatformConfig.name == item["name"]))
            if not existing.scalar_one_or_none():
                platform = PlatformConfig(
                    id=str(uuid.uuid4()),
                    name=item["name"],
                    base_url=item["base_url"],
                    api_key=item["api_key"],
                    enabled=item["enabled"],
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                session.add(platform)
        await session.commit()
        logger.info("默认平台配置已检查/创建")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。

    启动时: 初始化日志、创建数据库表、预热 HTTP 客户端、创建默认平台配置。
    关闭时: 关闭 HTTP 客户端连接。
    """
    logger.info("UniSub 后端启动中...")
    logger.info("调试模式: %s", config.debug)
    logger.info("CORS 来源: %s", config.cors_origins)

    # 初始化数据库表
    try:
        await init_db()
        logger.info("数据库表初始化完成")
    except Exception as e:
        logger.error("数据库初始化失败: %s", e)
        logger.warning("数据库不可用，应用仍会启动但数据库操作将失败")

    # 创建默认平台配置（tmdb 等）
    try:
        await _seed_default_platforms()
    except Exception as e:
        logger.error("默认平台配置创建失败: %s", e)

    # TMDB 缓存数据迁移（从旧表复制到独立 tmdb_cache 表）
    try:
        from app.services.tmdb_cache_migration import migrate_tmdb_cache

        await migrate_tmdb_cache()
    except Exception as e:
        logger.error("TMDB 缓存迁移失败: %s", e)

    # 启动后台调度器
    try:
        from app.services import scheduler as _scheduler_mod
        from app.services.scheduler_runners import (
            auto_subscribe_runner,
            full_scan_runner,
            light_scan_runner,
            sync_runner,
            tmdb_sync_runner,
        )

        # 从文件加载持久化的调度状态
        try:
            _scheduler_mod.load_state()
        except Exception as e:
            logger.error("调度状态加载失败: %s", e)

        await _scheduler_mod.start(
            light_scan_runner,
            full_scan_runner,
            auto_subscribe_runner=auto_subscribe_runner,
            sync_runner=sync_runner,
            tmdb_sync_runner=tmdb_sync_runner,
        )
    except Exception as e:
        logger.error("调度器启动失败: %s", e)

    yield

    # 关闭调度器
    try:
        from app.services import scheduler as _scheduler_mod

        await _scheduler_mod.stop()
    except Exception as e:
        logger.error("调度器关闭异常: %s", e)

    # 关闭 HTTP 客户端
    await http_client.close()
    logger.info("UniSub 后端已关闭")


app = FastAPI(
    title="UniSub — 统一媒体订阅聚合器",
    description="在 NextFind + MoviePilot 之上建一层订阅管理层",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 中间件（生产环境限定具体 methods/headers）
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)

# 注册路由
app.include_router(auto_subscribe.router)
app.include_router(logs.router)
app.include_router(platforms.router)
app.include_router(cd2.router)
app.include_router(search.router)
app.include_router(subscriptions.router)
app.include_router(dashboard.router)
app.include_router(emby.router)
app.include_router(tasks.router)
app.include_router(forward.router)


# 全局异常处理（排除 HTTPException，让 FastAPI 内置处理器处理）
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器 — 只处理非 HTTPException 的未预期异常。"""
    if isinstance(exc, (HTTPException,)):
        raise exc
    logger.error("未处理的异常 [%s %s]: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误", "error": str(exc) if config.debug else None},
    )


@app.get("/")
async def root():
    """根路径 — 健康检查。"""
    return {
        "service": "UniSub Backend",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    """健康检查端点（含 DB 连通性检测，DB 不可用时返回 503）。"""
    from sqlalchemy import text

    db_ok = True
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    status = "healthy" if db_ok else "degraded"
    payload = {"status": status, "database": "ok" if db_ok else "unavailable"}
    if db_ok:
        return payload
    return JSONResponse(status_code=503, content=payload)
