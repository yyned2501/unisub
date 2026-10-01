"""账号配置持久化 — 环境变量优先，JSON 文件仅作兼容回退（已废弃）。

生效顺序：环境变量 > JSON 文件。

⚠️ 废弃说明：``app/data/auth_config.json`` 以明文保存登录口令，属遗留载体
（.gitignore 挡住了提交，但挡不住日志/备份/误拷）。读写在后续阶段（S6）统一迁入
数据库；在此之前：

    - 新部署一律用 ``UNISUB_FORWARD_USERNAME`` / ``UNISUB_FORWARD_PASSWORD`` 注入；
    - 文件路径仍可读，但从文件取到凭据时会打一条 deprecation 警告；
    - ``save_auth_config`` 写文件时会在文件内标注 ``_deprecated``。
"""

import json
import os
from pathlib import Path

from app.core.logger import init_logger

logger = init_logger()

_ENV_USERNAME = "UNISUB_FORWARD_USERNAME"
_ENV_PASSWORD = "UNISUB_FORWARD_PASSWORD"

_AUTH_FILE = Path(__file__).resolve().parent.parent / "data" / "auth_config.json"

# 文件回退只提示一次，避免登录/信息接口高频调用刷屏
_deprecation_warned = False


def _ensure_file():
    """确保配置文件存在（不存在则写入空对象）。"""
    _AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _AUTH_FILE.exists():
        _AUTH_FILE.write_text("{}", encoding="utf-8")


def _read_auth_file() -> dict:
    """读取已废弃的 JSON 账号文件。

    Returns:
        文件内容字典；文件不存在、非字典或解析失败时返回空字典
    """
    global _deprecation_warned

    if not _AUTH_FILE.exists():
        return {}
    try:
        data = json.loads(_AUTH_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"读取账号配置失败: {e}")
        return {}
    if not isinstance(data, dict):
        return {}

    if (data.get("username") or data.get("password")) and not _deprecation_warned:
        _deprecation_warned = True
        logger.warning(f"账号配置取自已废弃的明文文件 {_AUTH_FILE}，请改用环境变量 {_ENV_USERNAME}/{_ENV_PASSWORD}")
    return data


def load_auth_config() -> dict:
    """加载生效的账号密码。

    优先级：环境变量 > JSON 文件（已废弃）。两者都为空时返回空字典。

    Returns:
        {"username": str, "password": str}，或空字典
    """
    env_username = os.getenv(_ENV_USERNAME, "").strip()
    env_password = os.getenv(_ENV_PASSWORD, "").strip()
    if env_username and env_password:
        return {"username": env_username, "password": env_password}

    file_auth = _read_auth_file()
    username = env_username or file_auth.get("username", "")
    password = env_password or file_auth.get("password", "")
    if not username and not password:
        return {}
    return {"username": username, "password": password}


def save_auth_config(username: str, password: str) -> None:
    """保存账号密码到 JSON 文件（仅兼容回退路径，已废弃）。

    ⚠️ 明文落盘。在数据库落库路径（S6）就绪前保留，文件内含 ``_deprecated`` 标注。

    Args:
        username: 用户名
        password: 密码
    """
    _ensure_file()
    try:
        _AUTH_FILE.write_text(
            json.dumps(
                {
                    "_deprecated": (
                        f"明文落盘已废弃，请改用环境变量 {_ENV_USERNAME}/{_ENV_PASSWORD}；后续版本将迁入数据库（S6）"
                    ),
                    "username": username,
                    "password": password,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        logger.warning(f"账号配置已写入已废弃的明文文件 {_AUTH_FILE}: username={username!r}")
    except OSError as e:
        logger.error(f"保存账号配置失败: {e}")
        raise


def get_effective_auth(config_username: str, config_password: str) -> tuple[str, str]:
    """获取生效的登录账号密码（load_auth_config 的兼容包装）。

    优先级：环境变量 > JSON 文件（废弃） > 传入的兜底值。

    Args:
        config_username: 兜底用户名
        config_password: 兜底密码

    Returns:
        (username, password)
    """
    auth = load_auth_config()
    return auth.get("username") or config_username, auth.get("password") or config_password
