"""NextFind 双向同步各阶段共用的状态判定工具。"""

from __future__ import annotations

# NF API 并发限流（避免压平 NextFind 服务）
_NF_CONCURRENCY = 5


def _parse_year(year_val: str | int | None) -> int | None:
    """安全解析年份值。

    Args:
        year_val: 原始年份值（字符串、数字或 None）

    Returns:
        整数年份或 None
    """
    if year_val is None:
        return None
    try:
        return int(year_val)
    except (ValueError, TypeError):
        return None


def _nf_status(entry: dict) -> str:
    """提取 NF 订阅状态（sub_status 优先，回退 status/nf_status），统一小写。

    Args:
        entry: NF 订阅数据字典

    Returns:
        小写状态字符串，缺失时为空串
    """
    raw = entry.get("sub_status") or entry.get("status") or entry.get("nf_status") or ""
    return str(raw).lower()


def _is_active_status(entry: dict) -> bool:
    """NF 条目是否处于活跃状态。"""
    return _nf_status(entry) in ("active", "subscribing")


def _is_cancelled_status(entry: dict) -> bool:
    """NF 条目是否处于已取消状态。"""
    return _nf_status(entry) in ("cancelled", "canceled", "stopped")
