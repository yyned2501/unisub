"""核心订阅流程行为测试 — subscribe / unsubscribe 的服务层与 API 层行为。

覆盖：
- OrchestratorService.subscribe 成功路径（本地记录 + NF 标记 + 活动日志）
- OrchestratorService.subscribe 重复订阅去重
- OrchestratorService.unsubscribe 成功删除与 NF 失败保留记录
- API 层 POST / DELETE /api/subscriptions 端到端行为（NextFind 桩注入）
"""

import pytest
from sqlalchemy import select

from app.models.activity_log import ActivityLog
from app.models.platform_config import PlatformConfig
from app.models.subscription import Subscription
from app.services import require_nf_service
from app.services.orchestrator import OrchestratorService


class FakeNfFull:
    """NextFindService 测试桩 — 可控的 add/remove 结果并记录调用。"""

    def __init__(self, add_result: dict | None = None, remove_result: dict | None = None):
        self.add_result = add_result if add_result is not None else {"id": "nf-100"}
        self.remove_result = remove_result if remove_result is not None else {}
        self.add_calls: list[int] = []
        self.remove_calls: list[int] = []

    async def add_subscription(self, tmdb_id: int, media_type: str | None = None, title: str | None = None) -> dict:
        self.add_calls.append(tmdb_id)
        return self.add_result

    async def remove_subscription(self, tmdb_id: int, media_type: str | None = None) -> dict:
        self.remove_calls.append(tmdb_id)
        return self.remove_result


# === 服务层 ===


async def test_subscribe_success_creates_local_record(db_session) -> None:
    """订阅成功：本地记录落库，nf_subscribed/nf_sub_id 更新，写入活动日志。"""
    orch = OrchestratorService(FakeNfFull())
    resp = await orch.subscribe(
        db_session, tmdb_id=42, title="测试剧", media_type="tv", year=2024, defer_upstream=False
    )

    assert resp.tmdb_id == 42
    assert resp.nf_subscribed is True
    assert resp.nf_sub_id == "nf-100"

    sub = (await db_session.execute(select(Subscription).where(Subscription.tmdb_id == 42))).scalar_one()
    assert sub.title == "测试剧"
    assert sub.source == "manual"

    logs = (await db_session.execute(select(ActivityLog).where(ActivityLog.action == "subscribe"))).scalars().all()
    assert len(logs) == 1
    assert logs[0].tmdb_id == 42


async def test_subscribe_duplicate_returns_existing(db_session) -> None:
    """重复订阅同一 tmdb_id：直接返回已有记录，不再调用 NextFind。"""
    nf = FakeNfFull()
    orch = OrchestratorService(nf)
    first = await orch.subscribe(db_session, tmdb_id=7, title="剧A", media_type="tv", defer_upstream=False)
    second = await orch.subscribe(db_session, tmdb_id=7, title="剧A", media_type="tv", defer_upstream=False)

    assert second.id == first.id
    assert nf.add_calls == [7]  # 第二次未调用 NF

    count = (await db_session.execute(select(Subscription).where(Subscription.tmdb_id == 7))).scalars().all()
    assert len(count) == 1


async def test_unsubscribe_success_deletes_record(db_session) -> None:
    """取消订阅成功：NF 移除后本地记录删除，写入 unsubscribe 活动日志。"""
    orch = OrchestratorService(FakeNfFull())
    resp = await orch.subscribe(db_session, tmdb_id=9, title="剧B", media_type="tv", defer_upstream=False)

    result = await orch.unsubscribe(db_session, resp.id)
    assert result["success"] is True
    assert await db_session.get(Subscription, resp.id) is None

    logs = (await db_session.execute(select(ActivityLog).where(ActivityLog.action == "unsubscribe"))).scalars().all()
    assert len(logs) == 1


async def test_unsubscribe_nf_failure_keeps_record(db_session) -> None:
    """NF 移除失败：保留本地记录，避免同步时重新创建。"""
    nf = FakeNfFull(remove_result={"error": "HTTP 500"})
    orch = OrchestratorService(nf)
    resp = await orch.subscribe(db_session, tmdb_id=11, title="剧C", media_type="tv", defer_upstream=False)

    result = await orch.unsubscribe(db_session, resp.id)
    assert result["success"] is False
    assert await db_session.get(Subscription, resp.id) is not None


async def test_unsubscribe_missing_record(db_session) -> None:
    """取消不存在的订阅记录：返回失败结果而非抛异常。"""
    orch = OrchestratorService(FakeNfFull())
    result = await orch.unsubscribe(db_session, "not-exist-id")
    assert result["success"] is False
    assert "不存在" in result["message"]


# === API 层 ===


@pytest.fixture
async def nf_api_client(client, db_session):
    """注入 NextFind 桩与已启用平台配置的 API 客户端。"""
    from app.main import app

    fake = FakeNfFull()
    db_session.add(PlatformConfig(name="nextfind", base_url="http://nf.test", api_key="k"))
    await db_session.commit()

    async def _override_nf():
        return fake

    app.dependency_overrides[require_nf_service] = _override_nf
    yield client, fake
    app.dependency_overrides.pop(require_nf_service, None)


async def test_api_create_and_delete_subscription(nf_api_client, db_session, auth_headers: dict[str, str]) -> None:
    """API 端到端：POST 创建订阅 201 落库（本地优先，上游待同步），DELETE 取消后记录删除。"""
    client, fake = nf_api_client

    payload = {"tmdb_id": 100, "title": "API 测试剧", "media_type": "tv", "year": 2025}
    resp = await client.post("/api/subscriptions", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    # 本地优先：请求不等 NF/MP，响应里 nf_subscribed 初值 False（后台任务随后推送）
    assert body["nf_subscribed"] is False
    assert body["nf_sub_id"] is None

    sub = (await db_session.execute(select(Subscription).where(Subscription.tmdb_id == 100))).scalar_one()
    assert sub.id == body["id"]

    resp = await client.delete(f"/api/subscriptions/{body['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert await db_session.get(Subscription, body["id"]) is None
    assert fake.remove_calls == [100]


async def test_api_create_subscription_nf_failure_still_creates_local(
    nf_api_client, db_session, auth_headers: dict[str, str]
) -> None:
    """API 端到端：NF 不可用不再让用户请求失败 — 201 + 本地记录保留。

    契约（2026-10-01）：本地记录是权威事实，NF 是最终一致的上游；
    上游失败由同步引擎（Phase 2 本地→NF）兜底重试，不阻塞用户。
    """
    client, fake = nf_api_client
    fake.add_result = {"error": "HTTP 500", "detail": "boom"}

    payload = {"tmdb_id": 200, "title": "失败剧", "media_type": "tv"}
    resp = await client.post("/api/subscriptions", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["nf_subscribed"] is False

    subs = (await db_session.execute(select(Subscription).where(Subscription.tmdb_id == 200))).scalars().all()
    assert len(subs) == 1
