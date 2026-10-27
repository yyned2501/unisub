# 解耦审计报告（Phase D / D1）

- 依据：`docs/SPEC-PROJECT-DECOUPLING.md`
- 性质：**只读审计**。本次未修改 `backend/app/`、`frontend/` 任何文件（验收命令见 §8）。
- 基线 commit：`7220c85`（工作区另有 `M backend/uv.lock` 与若干未跟踪 docs/scripts，非本次产生）
- 方法：AST 静态分析（不靠目测）。全部数字可复现，脚本见附录 A（落到 temp 目录运行，不进仓库）。

---

## 1. 事实基线（实测，与 SPEC §0 逐项核对）

| 项 | SPEC §0 | 实测 | 结论 |
|---|---|---|---|
| `backend/app` 手写 `.py` / 行数 | 102 / ≈11.9k | **103 / 12,190** | 一致（口径差 1 个文件） |
| 生成代码 | `clouddrive_pb2*.py` 11,404 行 | **2 文件 / 11,404 行** | 一致 |
| services 文件数 | 33 | **32**（另有 `services/__init__.py`） | 一致 |
| 同名函数跨文件组 | 列了 14 组 | **28 组 / 46 个 def** | SPEC 少列 14 组，见 §5.4 |
| 文件内重复 `emby.py sync_cache ×2` | 有 | **不存在，见 §2.1** | ❌ 事实有误 |
| 逆向依赖条数 | 目标 0 | **0（SPEC §2 三条禁止项全通过）** | ✅ |

分层文件数/行数：`core` 11/969、`models` 11/397、`schemas` 12/655、`routers` 14/1452、`services` 32/5582。

---

## 2. SPEC §0 事实校正（3 处，直接影响 D2 排批）

### 2.1 ❌「`emby.py` 文件内 `sync_cache` ×2」不成立

- `backend/app/services/emby.py:250` — `async def sync_cache(self, db)`，**3 行**，`return await sync_emby_cache(self, db)`（薄委托）。
- `backend/app/routers/emby.py:49` — `async def sync_cache(...)`，**12 行**，是 `POST /api/emby/sync-cache` 的**端点处理器**。
- 全文件扫描 `emby.py` 只有 **1 处** `def sync_cache`。
- 判定：跨文件「端点 vs 服务」的正常分层，**不是 R1**。按 SPEC §1 表 → **误判（禁止合并）**，写白名单。**D1 不排批**。

### 2.2 ❌「上游客户端 4 个，同一模式」口径不准

`backend/app/services/clouddrive2.py:16` **不是 HTTP 客户端**，也不走 header 鉴权——它是 `backend/app/core/clouddrive_client.py`（gRPC）的门面，`__init__` 只是 `self._client = CloudDriveClient(base_url, api_key)`。

真正的同构 HTTP 客户端是 **3 个**：`nextfind.py:45`、`moviepilot.py:47`、`emby.py:28`（+ `tmdb.py:24` 近似但用 query 鉴权）。R2 抽象范围据此收窄（见 §5.2.1）。

### 2.3 ⚠️ 同名统计：SPEC 少列 14 组

SPEC 列出的数字本身准确（`create_subscription ×4`、`test_connection ×4`、`fetch_async ×4`、`save_config ×4`、`load_config ×3`、`clear_history ×3`、`mask_api_key ×2` 全部复核通过）。但实测共 **28 组**，SPEC 未列的 14 组见 §5.4 全表（含 `_mask_api_key ×2`、`backfill_overview ×2`、`sync_cache ×2`、`search_media ×2`、`_fetch_text ×2`、`_parse_year ×2`、`delete_subscription ×2`、`get_history ×2`、`update_config ×2`、`update_task_config ×2`、`run ×2`、`get_status ×2`、`sync_subscriptions ×2`）。

---

## 3. 分层依赖审计（改前基线）

### 3.1 SPEC §2 禁止项 — **0 条违规** ✅

| 禁止项 | 实测命中 |
|---|---|
| `services/` → `routers/` | **0** |
| `core/` → `services/` | **0** |
| `auto_subscribe/pipeline/` → `routers/` | **0** |

→ D2 结束时该项仍应为 0，因此**这条不是 D2 的收益来源**（改前就已达标，不要为它做任何重构）。

### 3.2 额外检查：`models/` 反向依赖（SPEC 未列，10 例，**建议不动**）

`app.models.*` → `app.core.database`（取 `Base`），10 个 model 文件全部命中。SPEC §2 未禁止、且是 ORM 声明的必需依赖。断开需引入 `models/base.py` 中转 → 属「为看似统一做大抽象」，SPEC §3 明令禁止。**列为白名单，保留。**

### 3.3 循环依赖：运行时 **0**，类型环 3 对（良性，保留）

| 环 | 性质 | 证据 |
|---|---|---|
| `services.emby` ↔ `services.emby_cache_sync` | **类型环** | `emby_cache_sync.py:20 if TYPE_CHECKING: from app.services.emby import EmbyService` |
| `services.tmdb` ↔ `services.tmdb_cache` | **类型环** | `tmdb_cache.py:21 if TYPE_CHECKING: from app.services.tmdb import TMDBService` |
| `services.mp_sync` ↔ `services.mp_missing` | **类型环** | `mp_missing.py:20 if TYPE_CHECKING: from app.services.mp_sync import MpSyncEngine` |

三处均只在 `TYPE_CHECKING` 块内，运行时不构成环 → **不是缺陷，是拆分后的正确写法**。D2 不要「为了消环」把参数类型改成 `Any`。

### 3.4 耦合密度（供 D2 评估影响面）

- 入度 top：`core.logger` 52、`core.database` 27、`models.subscription` 16、`services.nextfind` 16、`services.tmdb` 16、`core.http_client` 15、`core.auth` 14。
  → **动 `core/http_client.py`、`core/logger.py`、`core/database.py` 影响面最大**；`models/subscription` 次之。
- 出度 top：`app.main` 25、`routers.emby` 14、`pipeline.runner` 12、`routers.subscriptions` 11、`services.orchestrator` 11。
- services 同层内部边 **108 条**，最密集的是 `auto_subscribe.pipeline.*` → `services.{nextfind,tmdb,ai_config,bangumi}`（跨簇依赖），但均不违反 §2。
- 观察项（**不建议本 spec 动**）：`services/auto_subscribe/service.py:12` 与 `services/scheduler_runners.py:10` 从包门面 `app.services` 取工厂函数，而 `app/services/__init__.py:17-21` 又 import 了 emby/forward/moviepilot/nextfind/tmdb。即「服务层 import 服务层包门面」。这是 `STANDARDS.md` 既定的工厂约定，改动收益低、回归面大（14 个模块都用该门面），**保留**。

---

## 4. 零引用文件清单（交 Phase 3，本卡不删）

**结论：零引用文件 = 0 个。**

按严格 import 语义（`import a.b` / `from a.b import c`，含包级 `from app.services import x`）扫描 `backend/app` 全部 103 个手写文件：
- 未命中任何引用且非 `__init__.py` 的文件：**0**；
- 唯一「无生产引用」的是 `app/main.py`（被 `tests/conftest.py` 等引用）——它是 ASGI 入口，**不是死代码**。

「准零引用」（引用者只有 `__init__.py` 转发或仅测试）5 个，全部是**合法的 re-export 链，禁止删**：

| 文件 | 唯一引用者 | 判定 |
|---|---|---|
| `services/auto_subscribe/pipeline/runner.py` | `pipeline/__init__.py` | 包公开入口，保留 |
| `services/nf_sync_phases/{nf_to_local,local_to_nf,completion}.py` | `nf_sync_phases/__init__.py` | 同上，保留 |
| `app/main.py` | `tests/conftest.py` 等 | ASGI 入口，保留 |

> **给 Phase 3 的结论：`backend/app` 里没有可删的「零引用文件」。** Phase 3 若按此口径执行，产出应为「无可删对象」；其收益应转到**未跟踪脚本**（§6）。

---

## 5. 重复 / 近似功能清单（逐条：`file:line` + 类别 + 依据 + 处置 + 影响面 + 风险 + 收益 + 批次）

### 5.0 复现方式

- R1（逐字重复）：366 个函数体归一化（去 docstring/注释/空行/折叠空白）后做精确哈希比对 → 2 组命中。
- R2（近似）：函数体 ≥5 行两两 `difflib.SequenceMatcher.ratio() ≥ 0.80` → 12 对命中。
- 同名：AST 全量 `def` 名索引（排除 `__init__.py`）→ 28 组。
- 脚本见附录 A。

---

### 5.1 R1 真重复（2 项，**建议合并**，批次 1）

#### R1-1 `_mask_api_key` 脱敏逻辑 4 份拷贝 / 2 文件 ★

| 位置 | 内容 |
|---|---|
| `backend/app/schemas/cd2.py:8` | 模块级 `_mask_api_key`（5 行） |
| `backend/app/schemas/platform.py:8` | 模块级 `_mask_api_key`（5 行） |
| `backend/app/schemas/cd2.py:42` | `@field_serializer("api_key")` → `mask_api_key`（3 行） |
| `backend/app/schemas/platform.py:47` | `@field_serializer("api_key")` → `mask_api_key`（3 行） |

- **依据（相同）**：`diff` 两文件前 15 行除模块 docstring 与首个类名外**逐字相同**；`if not key or len(key) <= 8: return "****"` / `f"{key[:4]}****{key[-4:]}"` 完全一致；两个 `field_serializer` 方法体也逐字相同。归一化哈希判定为精确重复组。
- **差异**：无。
- **调用方**：仅这两个 schema 文件内部（外部通过响应模型输出 `api_key` 字段）。
- **建议处置**：**合并** → 新建 `backend/app/schemas/common.py`（或放 `app/schemas/platform.py` 由 cd2 反向引用；推荐新建，避免再产生单向依赖），导出 `mask_api_key(value: str) -> str` 与 `MaskedApiKeyMixin`（提供 `@field_serializer`）。两处 `_mask_api_key` 删除，两处 serializer 改继承 Mixin。
- **影响面**：2 个文件 + 1 个新文件；对外 API 契约（响应字段值）**不变**。
- **风险**：**低**。`test_secret_mask_writeback.py`（6 例）覆盖的是服务层回写，不覆盖 serializer → 靠 **OpenAPI 快照 diff** 兜底（字段不变即安全）。
- **收益**：删 4 处实现（约 16 行 → 1 处 5 行 + Mixin 3 行），消除「改了 cd2 忘了 platform」的分叉风险（该风险已实际发生：`****` 判定在 `services/cd2_config.py:47` 与 `services/platform.py:88` 也各写了一遍，见 R2-3）。
- **批次**：**1**。

#### R1-2 TMDB 海报 URL 拼接 3 处，2 处绕过单点 ★

| 位置 | 角色 |
|---|---|
| `backend/app/services/poster.py:8` | **唯一入口** `build_tmdb_poster_url()`，`TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"`（`:5`） |
| `backend/app/services/tmdb_cache.py:53` | 内联 `f"https://image.tmdb.org/t/p/w500{poster_path}"` — 绕过入口 |
| `backend/app/services/tmdb.py:171` | 内联 `f"https://image.tmdb.org/t/p/w500{r['poster_path']}"` — 绕过入口 |

- **依据（相同）**：三处产出同一语义的 URL；常量字面量 `https://image.tmdb.org/t/p/w500` 在仓库出现 2 次（另有 `poster.py:15` 的 docstring 示例）。
- **差异**：`poster.py:8` 处理 `None`/空串返回 `None`；两处内联各自写了 `if poster_path else None`，语义等价。
- **调用方**：`poster.build_tmdb_poster_url` 已被 `services/subscription.py:19`、`services/emby_tmdb_update.py:19` 正确使用 → **入口已存在且有 ≥2 使用方**（满足 SPEC §2 抽象门槛），另两处是漏改。
- **建议处置**：**合并**（改 2 行导入 + 2 行调用）。`tmdb_cache.py:53` → `poster_url = build_tmdb_poster_url(poster_path)`；`tmdb.py:171` → `build_tmdb_poster_url(r.get("poster_path"))`。
- **影响面**：2 个文件、4 行；`tmdb.py` 需新增 import（注意 `tmdb.py` 已 import `tmdb_cache`，不引入环）。
- **风险**：**低**（行为等价；若将来改 `w500`→`w780`，这两处才不会再漏）。
- **收益**：补齐 AGENTS.md「能力唯一化」表中「海报 URL」一行（当前该表**没有**这一行，属能力表漏登记）。
- **批次**：**1**。

---

### 5.2 R2 近似重复（**建议抽象**；按收益/风险排序）

#### 5.2.1 HTTP 上游客户端鉴权/错误模板（3 源同构）— 批次 3

| 位置 | 鉴权 header | 其他 |
|---|---|---|
| `services/nextfind.py:45` | `{"X-API-Key", "accept"}` | `_check()` 错误判别 + `_raise_on_auth_error()` 401/403 抛错 |
| `services/moviepilot.py:47` | `{"X-API-Key", "accept"}` | + 熔断状态 `_conn_failures`/`_breaker_until` + `_guarded()` 包装 |
| `services/emby.py:28` | `{"X-Emby-Token", "accept"}` | + `_user_id` 缓存 |
| `services/tmdb.py:24` | **query `api_key`**（非 header） | + `base_url` 自动补 `/3` |

- **依据（相同）**：四者 `__init__(base_url, api_key)` 首两行逐字相同：`self.base_url = base_url.rstrip("/")` + `self.api_key = api_key`；三者再构造 `_headers`；调用一律 `http_client.<verb>(url, headers=self._headers, ...)` 并检查 `"error" in result`。
- **差异（必须保留）**：header 名（`X-API-Key` / `X-Emby-Token` / 无-header）、`tmdb` 的 query 鉴权与 `/3` 规整、`moviepilot` 的连接失败熔断（`_guarded`，有 `test_moviepilot_breaker.py` 4 例守护）、`emby` 的 `_user_id` 缓存、`nextfind` 的 401/403 中止 → **差异全部走构造参数 + 子类覆写，不能抹平**。
- **建议处置**：**抽象** → 新建 `backend/app/core/api_client.py`：`class ApiClientBase` 提供 `base_url`/`api_key`/`_headers`/`_check(result, empty, context)`/`_raise_on_auth_error(result)`；`nextfind`/`moviepilot`/`emby` 继承并只声明 `header_name`；`tmdb` 保持独立（query 鉴权差异太大，强行并入会引入 `auth_style` 分支）。
- **影响面**：`core/` +1 文件、`services/` 3 文件；`core` 入度会上升（新模块入度 3）。**不改任何对外方法签名**。
- **风险**：**中**。三源均为生产主通道，鉴权回归 = 全站不可用。必须有 `test_moviepilot.py`(12) / `test_moviepilot_breaker.py`(4) / Emby 相关测试全绿 + 冒烟四件事（订阅/取消/扫描/同步）真跑。
- **收益**：消除 3 份 `rstrip`+`_headers`+`_check` 重复（≈30 行）；后续新增上游只写差异化部分。
- **批次**：**3**（排在 R1 之后，Emby/TMDB 家族之前）。

#### 5.2.2 `core/http_client.py` 的 4 个 verb 近乎逐字重复 ★ — 批次 2

- 位置：`get` `:81`(13 行) / `post` `:181`(15 行) / `put` `:217`(13 行) / `delete` `:243`(15 行)；相似度实测 **0.933 / 0.973 / 0.939 / 0.949 / 0.959 / 0.937**（6 对均值 ≈0.95）。
- **依据（相同）**：四者均为 `client = await self._ensure_client()` → `safe_url = strip_query(url)` → `try: response = await client.<verb>(...)` → `raise_for_status()` → `json()`；两个 `except` 分支逐字相同（`HTTPStatusError` → `{"error": f"HTTP {code}", "detail": strip_query(str(e))}`；`Exception` → `{"error": "request_failed", ...}`）——**8 行异常处理代码 ×4 份**。
- **差异**：仅 HTTP 动词与是否传 `json=` body。
- **调用方**：15 个模块（入度 15，全后端统一出口）。
- **建议处置**：**抽象** → 新增 `async def _request(self, method: str, url, headers=None, params=None, json=None) -> dict`，4 个公开方法降为 1~2 行薄封装（**方法名/签名/契约完全不变**）。`get_text`/`get_bytes` 是**另一套契约（抛 `HttpRequestError`）**，`http_client.py:1-16` 的模块 docstring 明确区分 → **不要一起并**。
- **影响面**：**单文件**；但该文件被 15 个模块依赖，且契约是「错误字典不抛异常」。
- **风险**：**中**。缓解证据：`test_log_redaction.py`(6)、`test_moviepilot.py`(12)、`test_moviepilot_breaker.py`(4)、`test_decision_gate.py`(20) 均经 `http_client`；`strip_query` 脱敏是历史事故防线（`http_client.py:53-54` 注释），重构后必须保持每个 except 分支都过 `strip_query`。
- **收益**：净减 ≈30 行重复异常处理，4 个 verb 的错误行为从此只能有一份。
- **批次**：**2**。

#### 5.2.3 订阅落库构造：`Subscription(...)` 两处独立维护 — 批次 2

| 位置 | 场景 |
|---|---|
| `services/orchestrator.py:216`（`db.add` `:230`） | 手动/本地优先订阅 |
| `services/auto_subscribe/pipeline/subscription.py:55`（`db.add` `:70`） | 自动订阅（NF 先确认） |

- **依据（相同）**：两处都 (a) 先 `select(Subscription).where(tmdb_id == ...)` 预检重复；(b) 构造**同一组字段** `id=uuid4, tmdb_id, media_type, title, poster_url, year, nf_status=None, nf_missing_eps=0, created_at, updated_at`；(c) `log_activity(db, "subscribe", ...)`；(d) 显式 `db.flush()`。
- **差异（必须保留）**：`nf_subscribed`（`False` vs `True`）、`nf_sub_id`（`None` vs `remote.subscription_id`）、`source`（`"manual"` vs `"auto_subscribe"`）、**执行顺序**（本地先落库→上游后台补 vs 上游先确认→再落库）。
- **建议处置**：**抽象**（只抽「构造 + 落库」，**不动顺序**）→ `services/subscription_store.py::create_local_subscription(db, *, tmdb_id, media_type, title, poster_url, year, source, nf_subscribed, nf_sub_id)`；两处调用，差异走参数。
- **影响面**：`services/` 3 文件。
- **风险**：**中低**。`db.flush()` 的**先后顺序**与 FK 顺序是 2026-10-01 生产事故点（`orchestrator.py:232-236` 有长注释），必须原样保留；守护测试 `test_mp_mirror_fk.py`(3)、`test_local_first_subscribe.py`(4)、`test_subscription_flow.py`(7)。
- **收益**：消除 10 个字段的平行维护（新增字段只改一处）。
- **批次**：**2**。若时间紧可与 5.2.2 拆成两批。

#### 5.2.4 上游类型映射表 3 份（**建议保留**，白名单）

- `services/nextfind.py` `_TYPE_MAP`（`movie→电影` / `tv→剧集` / `all→全部`）、`services/moviepilot.py:28` `_to_mp_type`、`services/forward.py:24` `_to_internal_type`。
- **保留理由**：三者方向/词表不同（NF 中文枚举、MP 中文枚举、forward 反向中→内），**各上游枚举就是差异本身** → SPEC §1 判为 **R3 有意重复**，只统一签名。合并会造出「万能映射器」，违反 §3 禁止项。

#### 5.2.5 其余近似对（**建议保留**，逐条给出不进批次的理由）

| 对 | ratio | 位置 | 保留理由 |
|---|---|---|---|
| `rename_file` / `move_file` | 0.843 | `core/clouddrive_client.py:105` / `:154` | 不同 gRPC 请求类型与参数集（R3 适配器） |
| `get_subscription_detail` / `delete_subscription` | 0.974 | `services/moviepilot.py:221` / `:237` | GET vs DELETE，同源不同动词；抽 `_url()` 收益 < 阅读成本 |
| `get_aired_episode_count` / `get_next_air_date` | 0.969 | `services/tmdb.py:58` / `:91` | 结构相似但**各自独立请求 `/tv/{id}`**——合并属**性能优化**，SPEC §5 明列为非目标；若做需单独开卡（可顺手消除同一 tmdb_id 两次请求） |
| `light_scan_runner` / `full_scan_runner` | 0.843 | `services/scheduler_runners.py:31` / `:42` | 前置 `session + get_emby/tmdb + None 检查` 仅 3 行；抽 helper 收益极低 |
| `_fetch_text` | 0.820 | `auto_subscribe/douban.py:144` / `mikan.py:168` | 同型 helper，但二者已在 R3 白名单（各源独立解析）；上提到 `RankProvider` 属可选优化，**不进 D2**（避免与 R3 边界纠缠） |
| `forward_list_subscribes` / `forward_list_user_subscribes` | 精确相等 | `routers/forward.py:160` / `:175` | 同一服务方法的**多条路由别名**（forward 兼容层），body 2 行 → **误判，禁止合并** |

---

### 5.3 误判白名单（同名不同职责，**禁止合并** — 违反即破坏分层）

| 同名 | 位置 | 保留理由 |
|---|---|---|
| `create_subscription` ×4 | `routers/subscriptions.py:50`（HTTP 端点）/ `pipeline/subscription.py:27`（NF 先确认）/ `moviepilot.py:123`（MP API）/ `nextfind.py:126`（NF API） | 四层各自语义（SPEC §1 明列） |
| `subscribe` / `unsubscribe` / `sync` / `sync_subscriptions` | `services/mp_sync.py:44/72/89` ↔ `services/orchestrator.py:172/266/302` ↔ `services/nf_sync.py:49` | 引擎入口 vs 编排 vs 端点，接口对称但语义不同 |
| `sync_cache` ×2 | `services/emby.py:250`（薄委托）/ `routers/emby.py:49`（端点） | 见 §2.1 |
| `backfill_overview` ×2 | `services/emby.py:217`(3 行委托) / `services/emby_cache_sync.py:258`(39 行实现) | 已拆分的门面 + 实现 |
| `test_connection` ×4 | `core/clouddrive_client.py:23` / `services/clouddrive2.py:20` / `emby.py:40` / `moviepilot.py:287` | 各协议的探活本就不同 |
| `search` / `search_media` | `services/forward.py:139` / `services/tmdb.py:118`；`routers/search.py:21` / `services/moviepilot.py:103` | 输出契约不同（forward 归一化 NF 结果 / tmdb 归一化 TMDB 结果），合并即改契约 |
| `_parse_year` ×2 | `auto_subscribe/douban.py:119`（从**文本**抽年份，返回 `str`）/ `nf_sync_phases/common.py:9`（**数值**归一，返回 `int`） | 同名但语义完全相反 → 典型误判，**禁止合并** |
| `get_status` ×2 | `auto_subscribe/service.py:29` / `emby_scan.py:43` | 各自的内存状态字典 |
| `run` ×2 | `pipeline/runner.py:46` / `auto_subscribe/service.py:59` | 流水线执行 vs 服务层触发 |
| `load_config`/`save_config`/`update_config`/`clear_history`/`get_history` | `config_store.py:127/135/144/165/192/197` + `service.py:47/51/55` + `ai_config.py:49/55` + `routers/auto_subscribe.py:33/71/105` | 模块级便捷函数 = 对 `_default_store` 方法的**门面**（`config_store.py:192/197` 3 行/5 行），非重复实现 |
| `update_task_config` ×2 | `routers/tasks.py:98`（端点）/ `services/scheduler.py:138`（实现） | 端点 vs 服务 |
| `fetch_async` ×4 | `auto_subscribe/base.py:22`(ABC) + douban/maoyan/mikan | **R3 有意重复**（SPEC §1 明列），已有 `RankProvider` ABC + 注册表，**设计正确，不要动** |
| `get_seasons_map`/`update_cache_for_tv`/`get_season_completion`/`mask_api_key` | `tmdb.py:186/182/190`、`schemas/*:42/47` | 3 行薄委托，**`tmdb.py:5-6` docstring 明写「为保持调用方不变的薄委托」** → 保留（不改签名、不删门面） |

---

### 5.4 同名函数全量对照表（28 组 / 46 def，`file:line`(行数)）

`__init__` 14 · `_fetch_text` 2 · `_mask_api_key` 2 · `_parse_year` 2 · `backfill_overview` 2 · `clear_history` 3 · `create_subscription` 4 · `delete_subscription` 2 · `fetch_async` 4 · `get_history` 2 · `get_season_completion` 2 · `get_seasons_map` 2 · `get_status` 2 · `load_config` 3 · `mask_api_key` 2 · `run` 2 · `save_config` 4 · `search` 2 · `search_media` 2 · `subscribe` 2 · `sync` 2 · `sync_cache` 2 · `sync_subscriptions` 2 · `test_connection` 4 · `unsubscribe` 2 · `update_cache_for_tv` 2 · `update_config` 2 · `update_task_config` 2

（完整 `file:line` 明细由附录 A 脚本 `samename` 段再生）

---

### 5.5 前端

#### R1-F1 `onImgError` 双实现，行为已分叉 ★

| 位置 | 行为 |
|---|---|
| `frontend/src/utils/format.ts:35` | `el.style.display = 'none'`（隐藏） |
| `frontend/src/components/MediaCard.vue:14` | 替换 `img.src` 为内联 SVG 占位图 → **保留格子尺寸** |

- **依据（相同）**：同名、同职责（`<img>` 的 `@error` 兜底），都在组件里以 `@error="onImgError"` 绑定。
- **差异**：一个隐藏、一个占位图 → **视觉不一致**（同一失败图片在搜索页卡片 vs 订阅列表/Emby 列表表现不同）。共享实现的调用方 4 处（`SubDialog.vue:51`、`EmbySeriesItem.vue:28`、`SubscriptionsView.vue:120`、`Tmdb404View.vue:51`）都走 `utils/format.ts`，只有 `MediaCard.vue` 自己写了一份。
- **建议处置**：**合并**到 `utils/format.ts`（升级为 `onImgError(e, { placeholder?: string })`，`MediaCard` 传 placeholder），**但需 architect 先定视觉基线**（统一隐藏 or 统一占位图）——SPEC §5「不改前端视觉」。
- **风险**：**低（代码）／中（视觉）**：合并必然改变一侧视觉，故必须在 D2 由 architect 选一个默认行为。
- **批次**：D2 前端批（若 architect 判定「不动视觉」→ 转白名单 + 在 `AGENTS.md` 记录这是有意的双行为）。

#### 文档漂移（建议 D2 顺手修正，非代码）

- `AGENTS.md` 结构表中的 `frontend/src/composables/useAction.ts`（注释「loading 包装」）**不存在**——全仓 `rg useAction` 零命中。实际的通用 composable 是 `useIdSet` / `usePagedList` / `usePolling` / `useSettingsForm`。`PlatformSettings.vue:52-80` 的 `handleSave`/`handleTest` 手写了「set id → try → msg.success → catch → finally 清 id」模板 ×2，本可用统一 loading 包装消除——**但那需要先建 `useAction`**，属新增抽象，SPEC §2 要求「≥2 真实使用方」，当前只有这 2 处 → **暂列观察项，不进 D2**。
- `frontend/src/utils/common.ts` 未出现在 `AGENTS.md` 结构表中（实际存在且被 `PlatformSettings.vue:6` 使用）→ 文档修正项。

---

## 6. 未跟踪文件（`backend/scripts/`）— 交 Phase 3 判定

`git status` 显示 `?? backend/scripts/`，共 5 个脚本 + `__pycache__/`：

| 脚本 | 被文档引用 | 建议 |
|---|---|---|
| `jev_ab_probe.py` | `docs/SPEC-JEV-DECISION.md:11,90`、`docs/jev-replay-report.md:45,164` | **留**（可复跑探针，回归依赖） |
| `jev_replay_build.py` / `_veto.py` / `_veto_soft.py` / `jev_replay_eval.py` | `docs/jev-replay-report.md:5,188-195` | **留**（复现 JEV 回放产物的唯一路径） |
| `schema_drift_check.py` | `docs/ARCHITECTURE-REVIEW-2026-10-01.md:202,245` | **留**（门禁工具） |
| `scripts/__pycache__/` | — | **应删/应 ignore**（无引用） |

→ **无脚本建议删除**；建议 Phase 3 的动作是：把 5 个脚本纳入 git（连同上述 docs），并把 `backend/scripts/__pycache__/` 加入 `.gitignore`（本卡只读，未执行）。

---

## 7. 建议批次（D2 排批，风险从低到高，符合 SPEC §4）

| 批次 | 内容 | 文件数 | 净变化 | 风险 | 验收要点 |
|---|---|---|---|---|---|
| **1** | R1-1 mask 合并 + R1-2 poster 单点 + 能力表补 2 行（mask / poster） | 5（含 1 新建） | ≈ -25 行 | **低** | OpenAPI diff 空；`test_secret_mask_writeback.py` 绿 |
| **2** | R2-5.2.2 `http_client._request` 收敛 + R2-5.2.3 `create_local_subscription` | 4 | ≈ -35 行 | **中** | `test_log_redaction/test_moviepilot*/test_mp_mirror_fk` 绿；脱敏分支不漏 `strip_query` |
| **3** | R2-5.2.1 `core/api_client.py` 抽 HTTP 上游基座（3 源继承，tmdb 不动） | 4 | ≈ -30 行 | **中** | 冒烟四件事真跑；三源连接测试通过 |
| **4** | 前端 R1-F1（**需 architect 先定视觉基线**）+ 文档漂移修正 | 3 | ≈ -10 行 | 中（视觉） | `npm run build`；人工确认列表页视觉 |
| — | **不做**：Emby 家族（`emby_db`/`emby_cache_sync`/`emby_scan`/`emby_tmdb_update` 职责各自独立）、TMDB 薄委托、`fetch_async`（R3）、`clouddrive2`（gRPC 门面）、类型环、`models→core`、`app.services` 包门面 | — | 0 | — | SPEC §3「禁止为看起来统一做大抽象」 |

**每批**：`pytest -q` 全绿 + OpenAPI 快照 diff 空 + 冒烟四件事（订阅一部 / 取消一部 / 扫描一次 / 触发一次同步）。

---

## 8. 验收自检

```bash
test -f docs/decoupling-audit.md && wc -l docs/decoupling-audit.md
git status --short backend/app frontend   # 期望：空（审计未改代码）
```

本次实际结果：`git status --short backend/app frontend` **空**（唯一新增是本文档，位于 `docs/`）。
审计脚本全部落在 `~/scratch`，仓库内未新增脚本——**本卡零代码改动**。

基线绿（`cd backend && .venv/bin/python -m pytest -q`）：
```
205 passed in 8.38s
```
→ D2 各批次以此为回归基线（与 Phase 4B 交接记录的 205 例一致，确认工作区无并发污染）。

---

## 附录 A：可复现脚本（只读，落到任意 temp 目录运行）

```python
# audit.py — 复现本报告全部数字（只读，不写项目文件）
import ast, sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path("/home/hermes/projects/unisub")
BACKEND, APP = ROOT / "backend", ROOT / "backend" / "app"
SKIP = {"__pycache__", ".venv", "migrations", "node_modules"}

def iter_py(base, gen=False):
    for p in sorted(base.rglob("*.py")):
        if any(x in SKIP for x in p.parts): continue
        if not gen and p.name.startswith("clouddrive_pb2"): continue
        yield p

def mod_of(p): return ".".join(p.relative_to(BACKEND).with_suffix("").parts)

def norm(node, lines):
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str): body = body[1:]
    if not body: return []
    st, en = body[0].lineno, getattr(body[-1], "end_lineno", body[-1].lineno)
    return [" ".join(l.split()) for l in lines[st-1:en] if l.strip() and not l.strip().startswith("#")]

# --- samename + R1/R2 ---
funcs, by_name = [], defaultdict(list)
for p in iter_py(APP):
    src = p.read_text(encoding="utf-8", errors="replace"); lines = src.splitlines()
    try: tree = ast.parse(src)
    except SyntaxError: continue
    rel = str(p.relative_to(ROOT))
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append({"f": rel, "l": n.lineno, "n": n.name, "b": norm(n, lines)})
            if p.name != "__init__.py": by_name[n.name].append((rel, n.lineno))
print("### 同名跨文件（>=2 文件） ###")
for name, items in sorted(by_name.items()):
    if len({i[0] for i in items}) >= 2:
        print(f"[{name}] {len(items)} 次:", ", ".join(f"{a}:{b}" for a, b in sorted(items)))

g = defaultdict(list)
for x in funcs: g["\n".join(x["b"])].append(x)
print("\n### R1 逐字重复（>=2 行） ###")
for items in g.values():
    if len(items) >= 2 and len(items[0]["b"]) >= 2:
        print(" · ", " | ".join(f"{i['f']}:{i['l']} {i['n']}()" for i in items))

print("\n### R2 近似（ratio>=0.80, >=5 行） ###")
big = [x for x in funcs if len(x["b"]) >= 5]; blobs = ["\n".join(x["b"]) for x in big]
for i in range(len(big)):
    for j in range(i+1, len(big)):
        if big[i]["f"] == big[j]["f"] and abs(big[i]["l"]-big[j]["l"]) < 3: continue
        r = SequenceMatcher(None, blobs[i], blobs[j], autojunk=False).ratio()
        if r >= 0.80:
            print(f"  {r:.3f}  {big[i]['f']}:{big[i]['l']} {big[i]['n']}()  vs  {big[j]['f']}:{big[j]['l']} {big[j]['n']}()")

# --- 分层 + 零引用 + 环 ---
files = list(iter_py(BACKEND))
known = set()
for p in files:
    m = mod_of(p); known.add(m)
    if m.endswith(".__init__"): known.add(m[:-9])
src = {p: p.read_text(encoding="utf-8", errors="replace") for p in files}
graph, refs = defaultdict(set), defaultdict(set)
for p in files:
    me = mod_of(p); me = me[:-9] if me.endswith(".__init__") else me
    try: tree = ast.parse(src[p])
    except SyntaxError: continue
    for n in ast.walk(tree):
        t = []
        if isinstance(n, ast.Import): t = [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            base = ".".join(me.split(".")[:-n.level] + ([n.module] if n.module else [])) if n.level else (n.module or "")
            t = [base] + [f"{base}.{a.name}" for a in n.names]
        for x in t:
            if x in known and x != me:
                graph[me].add(x); refs[x].add(str(p.relative_to(BACKEND)))
viol = [(m, d) for m, ds in graph.items() for d in ds
        if (m.startswith("app.services") and d.startswith("app.routers"))
        or (m.startswith("app.core") and d.startswith("app.services"))
        or (".pipeline" in m and d.startswith("app.routers"))]
print(f"\nSPEC 禁止项违规 = {len(viol)}")
cyc = {tuple(sorted((a, b))) for a in graph for b in graph[a] if a in graph.get(b, ())}
print("2 元环:", sorted(cyc))
zero = [str(p.relative_to(ROOT)) for p in iter_py(APP)
        if p.name != "__init__.py" and not refs.get(mod_of(p))]
print("零引用文件:", zero or "无")
```

```bash
# 文档/脚本引用核查
rg -n "jev_replay|jev_ab_probe|schema_drift_check" --glob '!backend/scripts/**' .
rg -n "TYPE_CHECKING|_mask_api_key|image\.tmdb\.org" backend/app
```
