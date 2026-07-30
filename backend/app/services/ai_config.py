"""AI 配置持久化 — 独立 JSON 文件存储 + 模型列表获取。"""

from __future__ import annotations

import copy
import json
import os
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.core.http_client import http_client
from app.core.logger import init_logger

logger = init_logger(__name__)

DEFAULT_AI_CONFIG: dict[str, Any] = {
    "ai_assist_enabled": False,
    "ai_api_key": "",
    "ai_api_base": "",
    "ai_model": "gpt-4o-mini",
}
_AI_KEYS = frozenset(DEFAULT_AI_CONFIG)
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class AiConfigStore:
    """管理 AI 配置的独立 JSON 文件。"""

    def __init__(
        self,
        config_path: Path | None = None,
        legacy_config_path: Path | None = None,
    ) -> None:
        """初始化配置文件路径和线程锁。"""
        self._config_path = config_path or _DATA_DIR / "ai_config.json"
        self._legacy_config_path = legacy_config_path or _DATA_DIR / "auto_subscribe_config.json"
        self._lock = threading.RLock()

    def load_config(self) -> dict[str, Any]:
        """加载 AI 配置，并在首次读取时迁移旧配置中的 AI 字段。"""
        with self._lock:
            self._migrate_legacy_config()
            return copy.deepcopy(self._merge_with_defaults(self._read_json(self._config_path, "AI 配置")))

    def save_config(self, updates: Mapping[str, Any]) -> dict[str, Any]:
        """合并局部 AI 配置更新并原子持久化。"""
        with self._lock:
            self._migrate_legacy_config()
            current = self._merge_with_defaults(self._read_json(self._config_path, "AI 配置"))
            config = self._merge_with_defaults({**current, **dict(updates)})
            self._write_json(self._config_path, config)
            return copy.deepcopy(config)

    def _migrate_legacy_config(self) -> None:
        """首次使用时从旧自动订阅配置中迁移 AI 字段。"""
        if self._config_path.exists() or not self._legacy_config_path.exists():
            return

        legacy = self._read_json(self._legacy_config_path, "旧自动订阅配置")
        ai_config = {key: legacy[key] for key in _AI_KEYS if key in legacy}
        if not ai_config:
            return

        self._write_json(self._config_path, self._merge_with_defaults(ai_config))
        remaining = {key: value for key, value in legacy.items() if key not in _AI_KEYS}
        self._write_json(self._legacy_config_path, remaining)
        logger.info("AI 配置已从自动订阅配置迁移到独立文件")

    @staticmethod
    def _merge_with_defaults(config: Mapping[str, Any]) -> dict[str, Any]:
        """仅保留已定义的 AI 配置字段并补全默认值。"""
        return {**DEFAULT_AI_CONFIG, **{key: value for key, value in config.items() if key in _AI_KEYS}}

    @staticmethod
    def _read_json(path: Path, label: str) -> dict[str, Any]:
        """读取 JSON 对象，文件不存在或无效时返回空字典。"""
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
            logger.warning("%s文件不是 JSON 对象: %s", label, path)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("%s加载失败: %s", label, exc)
        return {}

    @staticmethod
    def _write_json(path: Path, data: Mapping[str, Any]) -> None:
        """通过临时文件原子写入 JSON。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)


_default_store = AiConfigStore()


def get_ai_config_store() -> AiConfigStore:
    """获取默认 AI 配置存储器。"""
    return _default_store


async def fetch_ai_models(api_base: str, api_key: str) -> list[dict[str, str]]:
    """获取兼容 OpenAI API 的模型列表。

    Args:
        api_base: API 基础地址
        api_key: API 密钥

    Returns:
        模型列表，每项包含 id 和 object 字段

    Raises:
        ValueError: API 返回错误信息
    """
    url = f"{api_base}/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    data: dict[str, Any] = await http_client.get(url, headers=headers)
    if "error" in data:
        raise ValueError("获取 AI 模型列表失败")

    models = data.get("data", [])
    return [
        {"id": item["id"], "object": item.get("object", "model")}
        for item in models
        if isinstance(item, dict) and item.get("id")
    ]
