"""编排服务测试 — 业务异常层次与订阅失败行为。"""

import pytest

from app.core.errors import AppError, UpstreamError
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


async def test_subscribe_nf_failure_raises_upstream_error(db_session) -> None:
    """NF 订阅失败时应抛业务异常 UpstreamError，而非 HTTPException。

    forward 等非 web 调用方不应收到 HTTP 语义异常。
    """
    orch = OrchestratorService(FakeNf({"error": "HTTP 500", "detail": "boom"}))
    with pytest.raises(UpstreamError):
        await orch.subscribe(db_session, tmdb_id=1, title="测试剧", media_type="tv")
