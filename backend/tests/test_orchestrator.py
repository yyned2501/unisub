"""编排服务测试 — 业务异常层次与订阅失败行为。"""

from sqlalchemy import select

from app.core.errors import AppError, UpstreamError
from app.models.activity_log import ActivityLog
from app.models.subscription import Subscription
from app.services.orchestrator import OrchestratorService


class FakeNf:
    """NextFindService 测试桩 — 可控的 add_subscription 结果。"""

    def __init__(self, result: dict):
        self.result = result

    async def add_subscription(self, tmdb_id: int, media_type: str | None = None, title: str | None = None) -> dict:
        return self.result


def test_upstream_error_is_app_error() -> None:
    """UpstreamError 应是 AppError 子类，携带 502 状态码与消息。"""
    err = UpstreamError("NF 订阅失败")
    assert isinstance(err, AppError)
    assert err.status_code == 502
    assert err.message == "NF 订阅失败"
    assert str(err) == "NF 订阅失败"


async def test_subscribe_nf_failure_keeps_local_record(db_session) -> None:
    """NF 订阅失败不再抛异常：本地订阅保留，仅记活动日志待同步引擎重试。

    契约（2026-10-01）：本地记录是权威事实，NF/MP 是最终一致的上游镜像；
    上游失败不得让用户请求失败，也不得回滚本地订阅。
    """
    orch = OrchestratorService(FakeNf({"error": "HTTP 500", "detail": "boom"}))
    resp = await orch.subscribe(db_session, tmdb_id=1, title="测试剧", media_type="tv", defer_upstream=False)

    assert resp.nf_subscribed is False
    sub = await db_session.get(Subscription, resp.id)
    assert sub is not None
    assert sub.nf_subscribed is False

    logs = (await db_session.execute(select(ActivityLog).where(ActivityLog.action == "subscribe"))).scalars().all()
    assert any("待重试" in log.message for log in logs)
