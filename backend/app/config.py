"""配置模块 — 从环境变量读取应用配置。"""

import json
import logging
import os
from dataclasses import dataclass, field


@dataclass
class UniSubConfig:
    """应用配置数据类，所有字段从环境变量读取并带有合理默认值。"""

    debug: bool = False
    database_url: str = "postgresql+asyncpg://unisub:unisub@192.168.31.10:5432/unisub"
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"])
    jwt_secret: str = "unisub-forward-jwt-secret"
    forward_username: str = "admin"
    forward_password: str = "password"
    proxy_url: str | None = None


def _ensure_env(key: str, default: str) -> str:
    """读取环境变量，如使用默认值则打 warning（延迟导入避免循环引用）。"""
    val = os.getenv(key) or default
    if val == default and key not in os.environ:
        logging.getLogger("unisub").warning("环境变量 %s 未设置，使用默认值（生产环境请务必配置）", key)
    return val


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

    jwt_secret = _ensure_env("UNISUB_JWT_SECRET", "unisub-forward-jwt-secret")
    forward_username = _ensure_env("UNISUB_FORWARD_USERNAME", "admin")
    forward_password = _ensure_env("UNISUB_FORWARD_PASSWORD", "password")
    proxy_url = os.getenv("UNISUB_PROXY_URL") or None

    return UniSubConfig(
        debug=debug,
        database_url=database_url,
        cors_origins=cors_origins,
        jwt_secret=jwt_secret,
        forward_username=forward_username,
        forward_password=forward_password,
        proxy_url=proxy_url,
    )
