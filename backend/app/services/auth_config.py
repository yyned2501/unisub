"""账号配置持久化 — JSON 文件存储。

保存项目自身的登录账号密码，优先级：文件 > 环境变量。
"""

import json
from pathlib import Path

from app.core.logger import init_logger

logger = init_logger()

_AUTH_FILE = Path(__file__).resolve().parent.parent / "data" / "auth_config.json"


def _ensure_file():
    _AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _AUTH_FILE.exists():
        _AUTH_FILE.write_text("{}", encoding="utf-8")


def load_auth_config() -> dict:
    """从文件加载账号密码。

    Returns:
        {"username": str, "password": str}，文件不存在时返回空字典
    """
    if not _AUTH_FILE.exists():
        return {}
    _ensure_file()
    try:
        return json.loads(_AUTH_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"读取账号配置失败: {e}")
        return {}


def save_auth_config(username: str, password: str) -> None:
    """保存账号密码到文件。

    覆盖已有配置。

    Args:
        username: 用户名
        password: 密码
    """
    _ensure_file()
    try:
        _AUTH_FILE.write_text(
            json.dumps({"username": username, "password": password}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"账号配置已保存: username={username!r}")
    except OSError as e:
        logger.error(f"保存账号配置失败: {e}")
        raise


def get_effective_auth(config_username: str, config_password: str) -> tuple[str, str]:
    """获取生效的登录账号密码。

    优先级：文件 > 环境变量

    Args:
        config_username: 环境变量中的用户名
        config_password: 环境变量中的密码

    Returns:
        (username, password)
    """
    file_auth = load_auth_config()
    username = file_auth.get("username") or config_username
    password = file_auth.get("password") or config_password
    return username, password
