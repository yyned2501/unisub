"""自动订阅 — 榜单来源基类 + 注册表。

各来源子类以类属性声明 provider_id / provider_name，用 @register 自注册；
fetch_async() 是异步方法，产出 RankMediaItem 列表。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.auto_subscribe.models import RankMediaItem


class RankProvider(ABC):
    """榜单来源基类。"""

    provider_id: str = ""
    provider_name: str = ""

    @abstractmethod
    async def fetch_async(self, options: dict) -> list[RankMediaItem]:
        """抓取 + 解析榜单，产出标准化条目（可能未带 tmdb id）。"""
        raise NotImplementedError

    @staticmethod
    def as_list(value) -> list[str]:
        """把多选值统一成字符串列表（兼容逗号分隔字符串）。"""
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return []

    @staticmethod
    def to_int(value, default: int = 0) -> int:
        """安全转 int，失败回退默认值。"""
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return default


# 来源注册表：provider_id -> 类。
REGISTRY: dict[str, type[RankProvider]] = {}


def register(cls: type[RankProvider]) -> type[RankProvider]:
    """把来源类登记到注册表（按 provider_id）。"""
    if cls.provider_id:
        REGISTRY[cls.provider_id] = cls
    return cls


def get_provider(provider_id: str) -> RankProvider | None:
    """按 id 取来源实例；未知返回 None。"""
    cls = REGISTRY.get(provider_id)
    return cls() if cls is not None else None
