"""配置模块 — 从环境变量读取应用配置。"""

import json
import logging
import os
import secrets
from dataclasses import dataclass, field


@dataclass
class UniSubConfig:
    """应用配置数据类，所有字段从环境变量读取并带有合理默认值。"""

    debug: bool = False
    database_url: str = "postgresql+asyncpg://unisub:unisub@192.168.31.10:5432/unisub"
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"])
    jwt_secret: str = ""
    proxy_url: str | None = None


def _jwt_secret_from_env() -> str:
    """读取 JWT 密钥；未配置时生成进程级随机密钥（不落盘、重启失效），避免代码中硬编码密钥。"""
    val = os.getenv("UNISUB_JWT_SECRET")
    if val:
        return val
    logging.getLogger("unisub").warning("环境变量 UNISUB_JWT_SECRET 未设置，已生成随机密钥（生产环境请务必配置）")
    return secrets.token_hex(32)


def parse_config() -> UniSubConfig:
    """从环境变量解析配置，缺失时使用默认值。

    环境变量:
        UNISUB_DEBUG: "true" 开启调试模式
        UNISUB_DATABASE_URL: PostgreSQL 连接字符串
        UNISUB_CORS_ORIGINS: JSON 数组，允许的跨域来源
    """
    debug = os.getenv("UNISUB_DEBUG", "false").lower() == "true"
    database_url = os.getenv(
        "UNISUB_DATABASE_URL",
        "postgresql+asyncpg://unisub:unisub@192.168.31.10:5432/unisub",
    )
    cors_origins_raw = os.getenv(
        "UNISUB_CORS_ORIGINS",
        '["http://localhost:5173","http://localhost:3000"]',
    )
    try:
        cors_origins = json.loads(cors_origins_raw)
    except (json.JSONDecodeError, TypeError):
        cors_origins = ["http://localhost:5173", "http://localhost:3000"]

    jwt_secret = _jwt_secret_from_env()
    proxy_url = os.getenv("UNISUB_PROXY_URL") or None

    return UniSubConfig(
        debug=debug,
        database_url=database_url,
        cors_origins=cors_origins,
        jwt_secret=jwt_secret,
        proxy_url=proxy_url,
    )
