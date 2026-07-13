"""UniSub 后端入口 — FastAPI 应用工厂。

负责:
    - 生命周期管理（启动初始化数据库、关闭清理 HTTP 客户端）
    - 注册所有路由
    - CORS 中间件
    - 全局异常处理
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import parse_config
from app.core.database import init_db
from app.core.http_client import http_client
from app.core.logger import init_logger
from app.routers import (
    dashboard,
    platforms,
    search,
    subscriptions,
    tasks,
)

config = parse_config()
logger = init_logger(config.debug)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。

    启动时: 初始化日志、创建数据库表、预热 HTTP 客户端。
    关闭时: 关闭 HTTP 客户端连接。
    """
    logger.info("UniSub 后端启动中...")
    logger.info(f"调试模式: {config.debug}")
    logger.info(f"CORS 来源: {config.cors_origins}")

    # 初始化数据库表
    try:
        await init_db()
        logger.info("数据库表初始化完成")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        logger.warning("数据库不可用，应用仍会启动但数据库操作将失败")

    yield

    # 关闭 HTTP 客户端
    await http_client.close()
    logger.info("UniSub 后端已关闭")


app = FastAPI(
    title="UniSub — 统一媒体订阅聚合器",
    description="在 NextFind + MoviePilot 之上建一层订阅管理层",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(platforms.router)
app.include_router(search.router)
app.include_router(subscriptions.router)
app.include_router(dashboard.router)
app.include_router(tasks.router)


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器 — 捕获未处理的异常并返回统一格式。"""
    logger.error(f"未处理的异常 [{request.method} {request.url.path}]: {exc}")
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
    """健康检查端点。"""
    return {"status": "healthy"}
