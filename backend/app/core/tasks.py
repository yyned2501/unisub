"""后台任务工具 — 统一创建带异常兜底的 asyncio 后台任务。"""

import asyncio
from collections.abc import Coroutine
from typing import Any

from app.core.logger import init_logger

logger = init_logger()

# 持有运行中的任务引用，防止被垃圾回收提前取消
_background_tasks: set[asyncio.Task] = set()


def spawn_background_task(coro: Coroutine[Any, Any, Any], name: str) -> asyncio.Task:
    """创建后台任务并登记异常兜底，避免未 await 的协程异常静默消失。

    Args:
        coro: 要后台执行的协程
        name: 任务名称（用于日志追踪）

    Returns:
        创建的 asyncio.Task
    """
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)

    def _on_done(t: asyncio.Task) -> None:
        _background_tasks.discard(t)
        if t.cancelled():
            logger.warning("后台任务已取消: %s", name)
            return
        exc = t.exception()
        if exc:
            logger.error("后台任务 %s 执行异常: %s", name, exc)

    task.add_done_callback(_on_done)
    return task
