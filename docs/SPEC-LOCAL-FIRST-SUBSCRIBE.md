# SPEC：订阅本地优先（用户请求不等 NF / MP 上游）

- 作者：architect ｜ 日期：2026-10-01 ｜ 状态：待 coder 实现/验收
- 仓库：`/home/hermes/projects/unisub`（后端 `backend/`）
- 前置提交：`d13bb9b`（FK 顺序 + MP 镜像 best-effort，已上线）
- 关联：本 spec 是 `docs/ARCHITECTURE-REVIEW-2026-10-01.md` 中 S-B 的实际落地版（B2 解耦 / B3 幂等 / B4 超时）

## 0. 需求与量级（实测，不是推断）

| 观测 | 数值 | 证据 |
|---|---|---|
| 电影订阅请求总耗时 | **12.4s / 13.0s** | `activity_logs`：17:54:52.987「订阅了 仙逆剧场版」→ 17:55:05.383「MP 镜像订阅」；17:55:41.998 → 17:55:54.981 |
| 其中 MP 建订阅 `POST /api/v1/subscribe/` | ≈12.3s（12.4 − find 0.06） | 真实客户端实测：`GET /subscribe/media/tmdb:1599191` 0.06s、`POST /mediaserver/notexists` 0.05s；`http_client` 无重试，只发一次 |
| 电视剧订阅请求耗时 | **1.1s** | 17:45:34.283「订阅了 伊甸之东 (tv)」→ 17:45:35.383「取消订阅」；全程无 MP 镜像事件（`query_missing_seasons` 无缺集 → 不调 MP） |
| 真的建过 MP 订阅的剧 | 15.3s / 18.2s | 09-05 死神 15.3s、08-04 Running Man 18.2s → 与电影同量级 |

结论：**不是"电影慢"，是"调 MP 建订阅要十几秒"，电影每次都调、电视剧大多数时候跳过**。MP 建订阅耗时不可控（第三方），只能不阻塞用户。

量级目标：订阅请求路径 p95 **< 500ms**（不得含任何出网调用）；订阅峰值 < 10 QPS；上游 MP 单次调用可达 15s+。

## 1. 组件边界

- **权威事实源**：PostgreSQL `subscriptions`（及子表 `mp_subscription`）—— 本地是唯一事实源。
- **下游镜像（最终一致）**：NextFind API、MoviePilot API。二者失败 = 待同步，不是失败。
- **后台任务**：`asyncio.Task`，**自建 DB 会话**（不共享请求会话），任务集合挂在 `OrchestratorService` 实例上（防 GC）。
- 不新增进程/队列/worker（非目标）。

## 2. 接口契约

| 接口 | 变更后行为 |
|---|---|
| `OrchestratorService.subscribe(..., defer_upstream=True)` | 本地 add → `flush` → 活动日志 → `commit` → 返回；NF/MP 推送丢后台任务 |
| `POST /api/subscriptions`、forward 订阅端点、Emby 缺集订阅 | 只等本地 commit；响应 `nf_subscribed=false` = **上游待同步**（不是失败） |
| NF 不可用（原 502 契约作废） | **201 + 本地记录保留**，活动日志记 `NF 订阅待重试: {title} ({media_type})` |
| 重复/并发订阅同一 tmdb_id | 幂等：返回已存在记录；撞 `ix_subscriptions_tmdb_id` 不报错、不新增行 |
| `DELETE`（`unsubscribe`） | **不变**（仍同步等 NF，失败保留本地记录）——非本次范围 |

- `defer_upstream=False`：内联执行上游推送（测试 / 需要确定性 `nf_subscribed` 的调用方）。
- 后台任务必须自吞所有异常（`_upstream_task` 包一层 try/except），不得把异常抛进事件循环。
- 无事件循环时（`asyncio.create_task` 抛 RuntimeError）退化为告警 + 交给同步引擎兜底。

## 3. 数据格式

- `subscriptions`：无字段新增。`nf_subscribed` 语义重定义为 **true = NF 已确认 / false = 待同步**。
- `mp_subscription`：不变（裸 FK 挂 `subscriptions.id`，父行必须先落库）。
- 活动日志 message 契约（日志消费者依赖）：
  - `订阅了 {title} ({media_type})` — 请求路径内写入
  - `NF 订阅待重试: {title} ({media_type})` — 仅失败时写入
  - `MP 镜像订阅: {title} ...` — 不变

## 4. 量级约束

- 请求路径禁止出网（NF / MP / TMDB 一律不得出现在返回前）。
- 单订阅后台工作量：1 次 NF `add_subscription` + 1..N 次 MP 建订阅（剧集按缺集季）。
- 兜底重试（已有，不需新建）：`NfSyncEngine` Phase 2（本地→NF，60 min）、`MpSyncEngine.sync`（电影缺镜像补建 / 剧集缺集季，60 min）。
- 上线后观察指标：`activity_logs` 中「NF 订阅待重试」占比 < 1%/天；`UniqueViolationError` 归零。

## 5. 非目标（这期明确不做）

- 不改 DB schema，不加队列 / 独立 worker 进程。
- 不改 `unsubscribe` 语义（取消仍同步确认 NF）。
- 不改 forward 对外响应结构（只改 `nf_subscribed` 的时序含义）。
- 不做 JEV 接入（Phase 4A/4B 独立）。
- 不做 MP 容器侧耗时治理（12s 属第三方行为，本 spec 只做"不等它"）。
- 不改 `http_client` 全局超时（原 S-B4 提议；本 spec 不含，另行评估）。

## 6. 验收命令（coder 执行，architect 复核）

```bash
# 1) 全量测试（含新增 4 条本地优先契约测试）
cd /home/hermes/projects/unisub/backend && unset UNISUB_DATABASE_URL && .venv/bin/python -m pytest -q
# 期望：185 passed（基线 181 + 新增 4）

# 2) 部署
supervisorctl restart unisub:unisub_backend && curl -s localhost:8002/health

# 3) 请求路径实测（硬证据，不看代码看行为）
#    从 forward 端点（或本地 curl）订一部**新**电影，记录耗时：
#      time curl -s -o /dev/null -w '%{time_total}' -X POST <forward 订阅端点> -H 'Authorization: ...' -d '{...}'
#    期望：< 1s（修复前同一端点 12~13s）
# 4) 上游确实在后台补上（等 60s 后查库）
#    subscriptions.nf_subscribed 转 true、mp_subscription 出现镜像行
# 5) 幂等：连点两次同一 tmdb_id → subscriptions 只有 1 行，日志无 UniqueViolationError
# 6) 日志中「订阅了 X」到「MP 镜像订阅: X」的间隔应出现在**请求返回之后**（后台完成）
```

## 7. 参考实现（未提交，在工作区，供复核）

`git status --short` / `git diff` 可见：

- `backend/app/services/orchestrator.py` — `subscribe(defer_upstream=True)` 本地优先 + `schedule_upstream/_upstream_task/drain_upstream/sync_upstream/_sync_upstream_inner`；`IntegrityError` 幂等兜底（flush 阶段触发，故 try 包住 flush+log+commit）
- `backend/tests/test_local_first_subscribe.py`（新，4 条）— 请求不等上游 / 上游异常保留本地 / 并发撞唯一索引幂等 / 内联模式
- `backend/tests/conftest.py` — 新增 `session_factory` fixture（后台任务注入内存库）
- `backend/tests/test_orchestrator.py`、`test_subscription_flow.py`、`test_mp_mirror_fk.py` — 契约变更后的断言

要求：以参考实现为基础**逐条对照本 spec 复核**（特别是第 2 节契约变更），跑通第 6 节验收后再 commit；若发现 spec 与参考实现冲突，以 spec 为准并在卡片里说明。

## 8. 连带复核：`d13bb9b`（FK 修复，已上线但未过 coder 的眼）

上一笔修复由 architect 越位代写并已上线（`d13bb9b`，test 从 0 → 181 passed）。本次要求 coder 连带复核，不重写、只查错：

- `git show d13bb9b` 全量复核 `backend/app/services/orchestrator.py` 与 `backend/tests/test_mp_mirror_fk.py`
- 重点核对三条：
  1. **FK 顺序**：`db.add(sub)` → `await db.flush()` 是否覆盖所有父行先落库的路径（movie/tv、forward/manual/auto/emby 各入口）
  2. **best-effort 契约**：MP 镜像 `begin_nested()` + try/except 是否真的不会连坐回滚本地订阅（本 spec 的 `_sync_upstream_inner` 沿用了同一模式，两处必须一致）
  3. **回归测试是否真的能挡住回归**：`test_mp_mirror_fk.py` 4 条用例，去掉修复后是否真的变 RED（coder 实测一次：临时回退修复跑测试，确认失败，再恢复）
- 结论写进卡片：通过 / 有问题（有问题则列出具体行号与复现命令）。**不通过时不要顺手改**，先报给 architect 定夺。

