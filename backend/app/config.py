"""配置模块 — 从环境变量读取应用配置。"""

import json
import os
from dataclasses import dataclass, field


@dataclass
class UniSubConfig:
    """应用配置数据类，所有字段从环境变量读取并带有合理默认值。"""

    debug: bool = False
    database_url: str = "postgresql+asyncpg://tgbot:tgbot@192.168.31.10:5432/unisub"
    cors_origins: list[str] = field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"]
    )


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
        "postgresql+asyncpg://tgbot:tgbot@192.168.31.10:5432/unisub",
    )
    cors_origins_raw = os.getenv(
        "UNISUB_CORS_ORIGINS",
        '["http://localhost:5173","http://localhost:3000"]',
    )
    try:
        cors_origins = json.loads(cors_origins_raw)
    except (json.JSONDecodeError, TypeError):
        cors_origins = ["http://localhost:5173", "http://localhost:3000"]

    return UniSubConfig(
        debug=debug,
        database_url=database_url,
        cors_origins=cors_origins,
    )
