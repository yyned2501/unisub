"""平台配置 CRUD 操作封装。

将 routers/platforms.py 中的数据库操作逻辑封装到此处，
遵循 routers → services → models 的调用链。
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_config import PlatformConfig


async def list_platforms(db: AsyncSession) -> list[PlatformConfig]:
    """获取所有平台配置列表。

    Args:
        db: 数据库会话

    Returns:
        平台配置列表
    """
    result = await db.execute(select(PlatformConfig).order_by(PlatformConfig.created_at))
    return list(result.scalars().all())


async def create_platform(
    db: AsyncSession, name: str, base_url: str, api_key: str, enabled: bool = True
) -> PlatformConfig:
    """创建平台配置。

    Args:
        db: 数据库会话
        name: 平台名称
        base_url: API 基础地址
        api_key: 鉴权密钥
        enabled: 是否启用

    Returns:
        创建的 PlatformConfig 对象

    Raises:
        ValueError: 平台名称已存在
    """
    existing = await db.execute(select(PlatformConfig).where(PlatformConfig.name == name))
    if existing.scalar_one_or_none():
        raise ValueError(f"平台 {name} 已存在")

    config = PlatformConfig(
        id=str(uuid.uuid4()),
        name=name,
        base_url=base_url,
        api_key=api_key,
        enabled=enabled,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


async def update_platform(db: AsyncSession, platform_id: str, update_data: dict) -> PlatformConfig | None:
    """更新平台配置。

    Args:
        db: 数据库会话
        platform_id: 平台配置 ID
        update_data: 要更新的字段字典

    Returns:
        更新后的 PlatformConfig，不存在时返回 None
    """
    config = await db.get(PlatformConfig, platform_id)
    if not config:
        return None

    for key, value in update_data.items():
        setattr(config, key, value)
    config.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(config)
    return config


async def delete_platform(db: AsyncSession, platform_id: str) -> bool:
    """删除平台配置。

    Args:
        db: 数据库会话
        platform_id: 平台配置 ID

    Returns:
        是否删除成功
    """
    config = await db.get(PlatformConfig, platform_id)
    if not config:
        return False

    await db.delete(config)
    await db.commit()
    return True
