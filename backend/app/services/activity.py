"""活动日志服务 — activity_logs 的统一写入口。

所有业务代码记录活动日志一律走 log_activity()，禁止在调用点直接构造
ActivityLog（uuid/时间戳等样板已在此收敛）。独立成模块（而非留在
services/__init__.py）以便 services 包内模块直接导入而不触发循环依赖。
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog


async def log_activity(
    db: AsyncSession,
    action: str,
    message: str,
    tmdb_id: int | None = None,
) -> None:
    """写入活动日志（仅加入会话，提交由调用方负责）。

    Args:
        db: 数据库会话
        action: 操作类型（subscribe / unsubscribe / sync / system 等）
        message: 日志消息
        tmdb_id: 关联的 TMDB ID（可选）
    """
    entry = ActivityLog(
        id=str(uuid.uuid4()),
        action=action,
        tmdb_id=tmdb_id,
        message=message,
        created_at=datetime.now(UTC),
    )
    db.add(entry)
