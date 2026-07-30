"""CloudDrive2 与平台配置密钥更新回归测试。

回归背景：GET 响应会将 api_key 脱敏为 ``xxxx****xxxx``，前端保存时把脱敏值
原样回传。service 层若无条件覆盖，真实密钥会被脱敏占位符替换，导致连接测试
报 ``UNAUTHENTICATED: Invalid auth token``。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.cd2_config import get_cd2_config, update_cd2_config
from app.services.platform import create_platform, update_platform

REAL_KEY = "c99e-really-long-secret-token-abc1b44"
MASKED_KEY = "c99e****1b44"  # GET 响应脱敏后的值，前端会原样回传


async def _seed_cd2_config(db_session: AsyncSession) -> None:
    """初始化一条带真实密钥的 CD2 配置。"""
    await get_cd2_config(db_session)
    await update_cd2_config(
        db_session,
        base_url="192.168.31.10:19798",
        api_key=REAL_KEY,
        target_path="/115open/待整理/转存/",
        enabled=True,
    )


async def test_cd2_update_with_real_key_persists(db_session: AsyncSession) -> None:
    """正向路径：传入真实密钥应正常保存。"""
    await _seed_cd2_config(db_session)

    config = await get_cd2_config(db_session)
    assert config.api_key == REAL_KEY


async def test_cd2_update_with_masked_key_keeps_original(db_session: AsyncSession) -> None:
    """回归：回传脱敏占位符不得覆盖已存储的真实密钥。"""
    await _seed_cd2_config(db_session)

    await update_cd2_config(
        db_session,
        base_url="192.168.31.10:19798",
        api_key=MASKED_KEY,
        target_path="/115open/待整理/转存/",
        enabled=True,
    )

    config = await get_cd2_config(db_session)
    assert config.api_key == REAL_KEY


async def test_cd2_update_with_empty_key_keeps_original(db_session: AsyncSession) -> None:
    """异常路径：回传空密钥应视为不修改，保留原密钥。"""
    await _seed_cd2_config(db_session)

    await update_cd2_config(
        db_session,
        base_url="192.168.31.10:19798",
        api_key="   ",
        target_path="/115open/待整理/转存/",
        enabled=True,
    )

    config = await get_cd2_config(db_session)
    assert config.api_key == REAL_KEY


async def test_cd2_update_replaces_with_new_real_key(db_session: AsyncSession) -> None:
    """正向路径：传入新的真实密钥应替换旧密钥。"""
    await _seed_cd2_config(db_session)
    new_key = "brand-new-secret-token-xyz999"

    await update_cd2_config(
        db_session,
        base_url="192.168.31.10:19798",
        api_key=new_key,
        target_path="/115open/待整理/转存/",
        enabled=True,
    )

    config = await get_cd2_config(db_session)
    assert config.api_key == new_key


async def test_platform_update_with_masked_key_keeps_original(db_session: AsyncSession) -> None:
    """回归：平台配置回传脱敏 api_key 不得覆盖真实密钥。"""
    platform = await create_platform(
        db_session, name="nextfind", base_url="http://192.168.31.10:8092", api_key=REAL_KEY
    )

    await update_platform(db_session, platform.id, {"api_key": MASKED_KEY, "base_url": "http://192.168.31.10:8092"})

    updated = await update_platform(db_session, platform.id, {})
    assert updated is not None
    assert updated.api_key == REAL_KEY


async def test_platform_update_with_new_real_key_persists(db_session: AsyncSession) -> None:
    """正向路径：平台配置传入新真实密钥应正常替换。"""
    platform = await create_platform(
        db_session, name="moviepilot", base_url="http://192.168.31.10:3000", api_key=REAL_KEY
    )
    new_key = "another-real-token-123456"

    updated = await update_platform(db_session, platform.id, {"api_key": new_key})

    assert updated is not None
    assert updated.api_key == new_key
