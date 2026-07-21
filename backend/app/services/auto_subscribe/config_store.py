"""自动订阅配置与运行历史的 JSON 持久化。"""

from __future__ import annotations

import copy
import json
import os
import re
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.core.logger import init_logger

logger = init_logger(__name__)

DEFAULT_CONFIG: dict[str, Any] = {
    "min_year": 0,
    "min_vote": 0,
    "min_popularity": 0,
    "media_type": "all",
    "enabled": False,
    "schedule_cron": "0 8 * * *",
    "douban_enabled": False,
    "douban_ranks": ["movie-hot-gaia", "tv-hot"],
    "douban_rsshub": "https://rss.awdys.cn",
    "douban_rss_custom": "",
    "douban_min_year": 0,
    "douban_min_vote": 0,
    "douban_media_type": "all",
    "mikan_enabled": False,
    "mikan_season": "当前",
    "mikan_year": 0,
    "mikan_resolve_detail": True,
    "mikan_min_year": 0,
    "mikan_min_vote": 0,
    "maoyan_enabled": False,
    "maoyan_movie_box": True,
    "maoyan_web_platforms": [],
    "maoyan_web_types": [],
    "maoyan_num": 10,
    "maoyan_min_year": 0,
    "maoyan_min_vote": 0,
    "maoyan_media_type": "all",
    "proxy_url": "",
}

DEFAULT_HISTORY: dict[str, Any] = {
    "handled": {},
    "last_run": None,
    "last_stats": {},
    "nf_cache": {},
}

_CRON_FIELD_RE = re.compile(r"^(?:\*|\d+|\d+-\d+)(?:/(?:\d+))?$")


def deep_merge(defaults: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    """递归合并默认值和覆盖值，覆盖值优先且不会共享可变对象。"""
    merged = copy.deepcopy(dict(defaults))
    for key, value in overrides.items():
        default_value = merged.get(key)
        if isinstance(default_value, Mapping) and isinstance(value, Mapping):
            merged[key] = deep_merge(default_value, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def validate_cron(expression: str) -> bool:
    """校验五字段 cron 表达式的基础数值语法。

    支持 ``*``、数字、数值范围、逗号列表和 ``/步长``；不支持名称别名。
    """
    if not isinstance(expression, str):
        return False
    fields = expression.split()
    if len(fields) != 5:
        return False

    limits = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
    return all(
        _validate_cron_field(field, minimum, maximum) for field, (minimum, maximum) in zip(fields, limits, strict=True)
    )


def _validate_cron_field(field: str, minimum: int, maximum: int) -> bool:
    """校验单个 cron 数值字段。"""
    for part in field.split(","):
        if not _CRON_FIELD_RE.fullmatch(part):
            return False
        value_part, _, step_part = part.partition("/")
        if step_part and not minimum < int(step_part) <= maximum - minimum + 1:
            return False
        if value_part == "*":
            continue
        if "-" in value_part:
            start, end = (int(value) for value in value_part.split("-", 1))
            if not minimum <= start <= end <= maximum:
                return False
        elif not minimum <= int(value_part) <= maximum:
            return False
    return True


class AutoSubscribeConfigStore:
    """管理自动订阅配置和历史记录的内存缓存及 JSON 文件持久化。"""

    def __init__(
        self,
        config_path: Path | None = None,
        history_path: Path | None = None,
        defaults: Mapping[str, Any] | None = None,
    ) -> None:
        """初始化存储器。

        Args:
            config_path: 配置文件路径，省略时使用应用 data 目录。
            history_path: 历史文件路径，省略时使用应用 data 目录。
            defaults: 配置默认值，可供测试或扩展模块注入。
        """
        data_dir = Path(__file__).resolve().parents[2] / "data"
        self._config_path = config_path or data_dir / "auto_subscribe_config.json"
        self._history_path = history_path or data_dir / "auto_subscribe_history.json"
        self._defaults = copy.deepcopy(dict(defaults or DEFAULT_CONFIG))
        self._config_cache: dict[str, Any] | None = None
        self._history_cache: dict[str, Any] | None = None
        self._lock = threading.RLock()

    def load_config(self) -> dict[str, Any]:
        """加载、迁移并以默认值补全自动订阅配置。"""
        with self._lock:
            if self._config_cache is None:
                raw = self._read_json(self._config_path, self._defaults, "配置")
                self._config_cache = self._normalize_config(raw)
            return copy.deepcopy(self._config_cache)

    def save_config(self, config: Mapping[str, Any]) -> dict[str, Any]:
        """校验、迁移并持久化完整或部分自动订阅配置。"""
        with self._lock:
            normalized = self._normalize_config(config)
            self._write_json(self._config_path, normalized)
            self._config_cache = normalized
            return copy.deepcopy(normalized)

    def update_config(self, updates: Mapping[str, Any]) -> dict[str, Any]:
        """深度合并局部配置更新并保存结果。"""
        with self._lock:
            return self.save_config(deep_merge(self.load_config(), updates))

    def load_history(self) -> dict[str, Any]:
        """加载并以默认结构补全运行历史。"""
        with self._lock:
            if self._history_cache is None:
                raw = self._read_json(self._history_path, DEFAULT_HISTORY, "历史")
                self._history_cache = deep_merge(DEFAULT_HISTORY, raw)
            return copy.deepcopy(self._history_cache)

    def save_history(self, history: Mapping[str, Any]) -> dict[str, Any]:
        """以默认结构补全并持久化运行历史。"""
        with self._lock:
            normalized = deep_merge(DEFAULT_HISTORY, history)
            self._write_json(self._history_path, normalized)
            self._history_cache = normalized
            return copy.deepcopy(normalized)

    def clear_history(self) -> dict[str, Any]:
        """清空运行历史并返回重置后的结构。"""
        return self.save_history(DEFAULT_HISTORY)

    def clear_cache(self) -> None:
        """清空内存缓存，使下一次读取重新加载文件。"""
        with self._lock:
            self._config_cache = None
            self._history_cache = None

    def _normalize_config(self, config: Mapping[str, Any]) -> dict[str, Any]:
        """合并默认值并校验定时表达式。"""
        normalized = deep_merge(self._defaults, config)
        cron = normalized.get("schedule_cron")
        if not validate_cron(cron):
            raise ValueError("schedule_cron 必须是有效的五字段 cron 表达式")
        return normalized

    @staticmethod
    def _read_json(path: Path, defaults: Mapping[str, Any], label: str) -> dict[str, Any]:
        """读取 JSON 对象；文件缺失或损坏时返回默认值。"""
        if not path.exists():
            return copy.deepcopy(dict(defaults))
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
            logger.warning("自动订阅%s文件不是 JSON 对象: %s", label, path)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("自动订阅%s加载失败: %s", label, exc)
        return copy.deepcopy(dict(defaults))

    @staticmethod
    def _write_json(path: Path, data: Mapping[str, Any]) -> None:
        """通过临时文件原子写入 JSON，避免中断时留下半截文件。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)


_default_store = AutoSubscribeConfigStore()


def get_config_store() -> AutoSubscribeConfigStore:
    """获取应用默认的自动订阅配置存储器。"""
    return _default_store


def load_config() -> dict[str, Any]:
    """加载默认存储器中的自动订阅配置。"""
    return _default_store.load_config()


def save_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """保存默认存储器中的自动订阅配置。"""
    return _default_store.save_config(config)


def load_history() -> dict[str, Any]:
    """加载默认存储器中的自动订阅运行历史。"""
    return _default_store.load_history()


def save_history(history: Mapping[str, Any]) -> dict[str, Any]:
    """保存默认存储器中的自动订阅运行历史。"""
    return _default_store.save_history(history)
