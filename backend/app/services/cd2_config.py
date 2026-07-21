"""CloudDrive2 配置服务。"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cd2_config import Cd2Config

DEFAULT_TARGET_PATH = "/115open/待整理/转存/"


async def get_cd2_config(db: AsyncSession) -> Cd2Config:
    """获取 CloudDrive2 配置，不存在时创建默认配置。"""
    result = await db.execute(select(Cd2Config).order_by(Cd2Config.created_at).limit(1))
    config = result.scalar_one_or_none()
    if config:
        return config

    config = Cd2Config(
        base_url="",
        api_key="",
        target_path=DEFAULT_TARGET_PATH,
        enabled=True,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


async def update_cd2_config(
    db: AsyncSession,
    base_url: str,
    api_key: str,
    target_path: str,
    enabled: bool,
    path_prefix: str = "",
    path_replacement: str = "",
) -> Cd2Config:
    """保存 CloudDrive2 配置。"""
    config = await get_cd2_config(db)
    config.base_url = base_url.strip().rstrip("/")
    config.api_key = api_key.strip()
    config.target_path = normalize_target_path(target_path)
    config.path_prefix = path_prefix.strip()
    config.path_replacement = path_replacement.strip()
    config.enabled = enabled
    config.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(config)
    return config


def normalize_target_path(target_path: str) -> str:
    """规范化 CloudDrive2 目标目录路径。"""
    normalized = target_path.strip()
    if not normalized:
        raise ValueError("移动目标位置不能为空")
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if normalized != "/":
        normalized = normalized.rstrip("/") + "/"
    return normalized
