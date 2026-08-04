"""活动日志统一写入口测试。"""

from sqlalchemy import select

from app.models.activity_log import ActivityLog
from app.services.activity import log_activity


async def test_log_activity_writes_entry(db_session):
    """写入条目应生成 UUID 主键并保留全部字段。"""
    await log_activity(db_session, "sync", "双向同步完成", tmdb_id=123)
    await db_session.commit()

    rows = (await db_session.execute(select(ActivityLog))).scalars().all()
    assert len(rows) == 1
    entry = rows[0]
    assert entry.action == "sync"
    assert entry.message == "双向同步完成"
    assert entry.tmdb_id == 123
    assert len(entry.id) == 36  # UUID 字符串
    assert entry.created_at is not None


async def test_log_activity_tmdb_id_optional(db_session):
    """tmdb_id 缺省为 None，不阻塞写入。"""
    await log_activity(db_session, "system", "自动订阅完成")
    await db_session.commit()

    entry = (await db_session.execute(select(ActivityLog))).scalar_one()
    assert entry.tmdb_id is None
