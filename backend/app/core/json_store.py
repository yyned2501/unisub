"""通用 JSON 文件读写工具。

统一各配置存储（自动订阅配置、AI 配置等）重复实现的 JSON 读取与原子写入逻辑。
"""

from __future__ import annotations

import copy
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.core.logger import init_logger

logger = init_logger(__name__)


def read_json_object(path: Path, label: str, defaults: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """读取 JSON 对象文件；文件缺失或损坏时返回默认值。

    Args:
        path: JSON 文件路径
        label: 日志中使用的文件标签（如 "自动订阅配置"）
        defaults: 不可读时返回的默认值，缺省为空字典

    Returns:
        解析出的字典；不可读时返回 defaults 的深拷贝
    """
    fallback: dict[str, Any] = copy.deepcopy(dict(defaults)) if defaults else {}
    if not path.exists():
        return fallback
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        logger.warning("%s文件不是 JSON 对象: %s", label, path)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("%s加载失败: %s", label, exc)
    return fallback


def write_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
    """通过临时文件原子写入 JSON，避免中断时留下半截文件。

    Args:
        path: 目标文件路径（父目录不存在时自动创建）
        data: 要写入的字典数据
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)
