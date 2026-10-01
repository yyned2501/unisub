"""登录失败计数与锁定 — 进程内滑动窗口计数 + 指数退避锁定。

用途：保护 ``POST /api/v1/login/access-token``，阻断对本地账号的离线爆破。

规则:
    - 同一 key 在 :data:`FAILURE_WINDOW` 秒内累计 :data:`MAX_FAILURES` 次失败即触发锁定；
    - 首次锁定 :data:`BASE_LOCK_SECONDS`（5 分钟），此后每再触发一次锁定时长翻倍，
      上限 :data:`MAX_LOCK_SECONDS`；
    - 登录成功即清零该 key 的计数与锁定级别。

约束:
    状态保存在进程内（与「后端单进程单实例」的部署约束一致）；
    若将来改为多进程部署，各进程独立计数，需换成 DB/Redis 共享状态。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

FAILURE_WINDOW = 300.0  # 失败计数窗口（秒）
MAX_FAILURES = 5  # 窗口内达到该次数即锁定
BASE_LOCK_SECONDS = 300.0  # 首次锁定时长（秒）
MAX_LOCK_SECONDS = 1800.0  # 锁定时长上限（秒）
_MAX_KEYS = 4096  # 状态表容量上限，超出时清理已过期条目


@dataclass
class _State:
    """单个 key 的失败计数与锁定状态。"""

    failures: list[float] = field(default_factory=list)
    locked_until: float = 0.0
    lock_level: int = 0


_states: dict[str, _State] = {}


def _now() -> float:
    """取单调时钟，避免系统时间回拨导致锁定提前失效。"""
    return time.monotonic()


def _prune(now: float) -> None:
    """状态表超出容量上限时清理已过期条目，防止无界增长。"""
    if len(_states) <= _MAX_KEYS:
        return
    expired = [key for key, state in _states.items() if state.locked_until <= now and not state.failures]
    for key in expired:
        _states.pop(key, None)


def is_locked(key: str) -> tuple[bool, int]:
    """查询 key 是否处于锁定期。

    Args:
        key: 限流键（调用方自行构造，如 ``ip|username``）

    Returns:
        ``(是否锁定, 剩余锁定秒数)``；未锁定时剩余秒数为 0
    """
    state = _states.get(key)
    if state is None:
        return False, 0
    now = _now()
    if state.locked_until <= now:
        return False, 0
    return True, int(state.locked_until - now) + 1


def record_failure(key: str) -> None:
    """记录一次登录失败；窗口内累计达阈值时进入锁定。

    Args:
        key: 限流键
    """
    now = _now()
    _prune(now)
    state = _states.setdefault(key, _State())
    state.failures = [t for t in state.failures if now - t <= FAILURE_WINDOW]
    state.failures.append(now)

    if len(state.failures) >= MAX_FAILURES:
        state.lock_level += 1
        state.locked_until = now + min(BASE_LOCK_SECONDS * (2 ** (state.lock_level - 1)), MAX_LOCK_SECONDS)
        state.failures.clear()


def reset(key: str) -> None:
    """登录成功后清零该 key 的失败计数与锁定级别。

    Args:
        key: 限流键
    """
    _states.pop(key, None)


def reset_all() -> None:
    """清空全部限流状态（供测试与运维使用）。"""
    _states.clear()
