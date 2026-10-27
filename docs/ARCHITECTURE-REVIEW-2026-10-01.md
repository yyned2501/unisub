# UniSub 架构评审与优化 Spec

> 评审人：Architect（architect profile）
> 日期：2026-10-01
> 方法：实机取证（进程 / 生产库 / 日志 / git / 测试运行），非读文档推断
> 交付性质：**spec**，不是"一张图几句话"。每项含证据、目标、动作、红线、验收。

---

## 0. 结论先行

1. 骨架是对的：三层解耦落地、平台配置快照缓存、图片改 HMAC 代理、测试 160 例。**不需要重构，需要收敛。**
2. 当前最大风险不在代码结构，在三处：**公开仓库明文凭据**、**无迁移机制导致的 schema 漂移**、**调度器无失败退避造成 10 秒级重试风暴**。
3. 架构当前成立的前提是"单进程"，但这条约束**没有写在任何地方**——这是最容易被后续"顺手优化"（workers>1、加本地缓存）击穿的地方。

---

## 1. 现状快照（实测数据）

### 1.1 进程拓扑

```
systemd(supervisor.service) → supervisord
  ├─ unisub:unisub_backend  → deploy/start-api.sh → uv run uvicorn app.main:app :8002  (单进程, pid 930)
  └─ unisub:unisub_frontend → nginx -c deploy/nginx.conf :8082 (静态 dist + /api 反代 :8002)
```

### 1.2 代码量

- 后端 `app/**/*.py` 22,724 行（其中 CD2 gRPC 生成代码 11,404 行 → 业务码 ≈ 11,300 行）
- 前端 `frontend/src` 5,529 行；产物 dist 6.3 MB
- 15 个 router / 40+ 个 service 文件 / 11 个 ORM model / 20 个测试文件

### 1.3 生产库实况（192.168.31.10:5432/unisub）

| 表 | 行数 | 说明 |
|---|---|---|
| emby_season_cache | 5,621 | 无保留策略 |
| activity_logs | 4,796 | 无保留策略，只增不减 |
| tmdb_cache | 3,669 | |
| emby_cache | 3,613 | |
| tmdb_season | 553 | |
| subscriptions | 436 | |
| mp_subscription | 285 | |
| platform_configs | 4 | nextfind / moviepilot / tmdb / emby |
| emby_blacklist | 3 | |
| cd2_configs | 1 | |

### 1.4 外部依赖

NextFind OpenAPI(192.168.31.10:8092) + NextFind Web + MoviePilot(192.168.31.10:3000) + TMDB(经 192.168.31.8:8000 自建代理) + Emby + CloudDrive2(gRPC) + AI(192.168.31.10:63000)

### 1.5 定时任务（进程内调度器，10s tick）

| 任务 | 配置间隔 | 实测（09-30） |
|---|---|---|
| 全量扫描 | 60 min（应 24 次/天） | **50 次**（近 7 天 53~62 次） |
| 轻量刷新 | 10 min | 正常 |
| NF 订阅同步 | 60 min | 正常 |
| TMDB 增量 | 60 min | 正常 |
| 自动订阅 | cron 表达式 | 正常 |

---

## 2. 成立的设计（保留，不要动）

| 设计 | 为什么对 |
|---|---|
| routers → services → core 三层 | 实测 `httpx` 零越界、services 零反向引用 routers；`make lint-backend` 用 import-linter 做门禁，规则可执行而非口头 |
| 平台配置缓存存**纯数据快照**而非 ORM 对象 | 规避跨会话 DetachedInstanceError，60s TTL 明确 |
| Emby 图片改 HMAC 签名代理 | 历史上 api_key 直拼进浏览器 URL 泄漏，已收敛为服务端代理 + `exp` 过期 + `sig` 校验，正确 |
| `AppError` 统一异常 + 全局兜底处理器 | 业务异常与 500 分离，Fluent 契约 |
| auto_subscribe/ 子包 + pipeline/ 分层 | 服务层唯一做了"域分组"的地方，是后续重构的范式 |
| 前端 composables 抽象（usePolling 自动清理、useAction、useIdSet） | 三处真实 bug（定时器未清理、未处理 rejection）已被这批抽象收编 |

---

## 3. 主要矛盾（按严重度，每条带证据）

### P0-1 公开仓库存在明文凭据（3 类，7 处）

证据：
- `curl https://api.github.com/repos/yyned2501/unisub` → `"private": false`，**仓库是公开的**
- `git grep -n "***REMOVED***"` → 4 个已跟踪文件命中：`AGENTS.md:70`、`CLAUDE.md:70`、`backend/app/references/nextfind-api-v2.md:26,163`、`nextfind-api-v3.md:734`
- NF OpenAPI Key `zv8icxx…`（明文）出现在 `nextfind-api-v2.md:25,37`、`nextfind-api-v3.md:28`
- 115 分享链接含 `password=<已脱敏>` 出现在 `nextfind-api-v3.md:369`

判定：这不是"技术债"，是**实时泄漏**。凭据已随 git 历史永久可检索，改文件不等于清除。

### P0-2 密钥进日志

证据：`logs/unisub.log` 实测行
```
[ERROR] (tmdb.py:53): TMDB 请求失败 [/tv/317955]: {'error': 'HTTP 404', 'detail': "… for url 'http://192.168.31.8:8000/3/tv/317955?api_key=<已脱敏>…'"}
```
成因：`services/tmdb.py:53` 把 httpx 的错误 detail（含完整 query string）整条落盘。logs/ 已 21 MB、保留 30 天。任何能读日志的人拿到 TMDB key。

### P0-3 登录凭据明文落盘 + 登录端点无频率限制

证据：
- `backend/app/data/auth_config.json`（54 B，明文 `{"username","password"}`），由 `services/auth_config.py` 直接读写
- `POST /api/v1/login/access-token` 无鉴权、无失败计数、无锁定（`routers/forward.py:48`）

判定：LAN 内可离线爆破；`.gitignore` 挡住了提交，但没挡住日志/备份/误拷。

### P1-4 迁移机制缺位 → 已发生 schema 漂移

证据：
- `core/database.py:init_db()` 只有 `Base.metadata.create_all`（**只建表，不改表**）
- `migrations/00X_*.sql` 共 6 个文件，全仓库**没有任何代码引用它们** → 靠人手执行
- 实机 drift 校验（用 `Base.metadata` 对 `information_schema` 逐列比对）：
  ```
  emby_cache: 库里多出 5 列 ['poster_url','tmdb_aired_eps','tmdb_next_air_date','tmdb_poster_path','tmdb_total_eps'] —— 模型未声明
  ```

判定：现状是"能跑但不可复制"。换机部署得到的是**缩减版表结构**（5 列丢失）；往模型加字段也不会自动落到存量库，直接 500。这是本轮最需要补的基础设施。

### P1-5 调度器无失败退避 → 10 秒级重试风暴（实测已发生）

证据（`logs/unisub.log.2026-09-30` 05:02 起）：
```
05:02:09 调度器触发全量扫描: 间隔 60 分钟
05:02:09 调度器循环异常: [Errno 111] Connection refused
05:02:19 调度器触发全量扫描: 间隔 60 分钟
05:02:19 调度器循环异常: [Errno 111] Connection refused
…（每 10 秒一次，持续到依赖恢复）
```
量化：全量扫描应 24 次/天，实测 50~62 次/天；近 7 天每天 26~35 条 `调度器循环异常`。

根因（`services/scheduler.py:211-225`）：`_last_full_run` 在 `await full_scan_runner()` **成功返回后**才赋值；异常走 `except` → 下一轮（10s）判定"从未运行过" → 立即重试。**失败路径无退避、无上界**，把一次依赖抖动放大成持续重试。

### P1-6 配置持久化三套并存

| 载体 | 内容 | 问题 |
|---|---|---|
| PostgreSQL | platform_configs / cd2_configs | 有事务，正确 |
| JSON 文件 `app/data/` | auth_config.json、ai_config.json、auto_subscribe_config.json、auto_subscribe_history.json(169 KB)、scheduler_state.json | 无事务、无锁、无多进程安全、不进备份 |
| .env | DB URL / CORS / JWT | 合理 |

### P2-7 "单进程"隐含约束未显式化

依赖进程内状态的位置：`services/__init__.py:54` 平台缓存、`scheduler.py:32` `_task_config`、`scheduler.py:25` `_auto_subscribe_last_slot`、`config_store.py` 配置/历史缓存、`EmbyScanService.get_status()` 运行标志、`data/*.json`。

判定：uvicorn 一旦 `workers>1` 或起第二个实例，会同时出现"定时任务重复执行 + 配置自相矛盾 + 平台缓存各说各话"。当前约束只存在于"我们知道"，没写进任何文档/断言。

### P2-8 重启即无条件全量扫描

证据：`_last_full_run = None` 在每次进 `_loop` 时重置；日志显示每日 04:00 定时更新重启后，04:00:12 立即触发全量扫描（对 3,600+ 剧集的 Emby 全套拉取）。

### P2-9 扫描与 HTTP 共用一个事件循环

`services/emby_cache_sync.py` 在事件循环内分页拉 `Limit=50000` 的 Episode 全量（实测一轮覆盖 3,613 部剧），期间同进程所有 API 请求排队等待。

### P3-10 文档与事实不符（评审失效）

`ARCHITECTURE.md`（306 行）描述：Element Plus、Docker Compose、alembic、4 个 router、3 个 service、`stores/app.js`。实际：Naive UI、supervisor、手工 SQL、15 个 router、40+ service。**由 AI 或新人照此文档产出的东西一定是错的。**

### P3-11 规范自相矛盾

`backend/app/STANDARDS.md:1.3` 铁律："`from sqlalchemy import ...` 在 core/ 以外 = 禁止"。实测：11 个 `models/*.py` 全部 import sqlalchemy（ORM 声明必需）。规则与事实冲突 → 规则失去约束力。

### P3-12 其余

- `tests/test_health.py` 自建 `client` fixture，**绕过 conftest 的 `get_db` override** → `/health` 直连生产 PG；实测唯一失败用例（`assert 503 == 200`，asyncpg "Event loop is closed"）。160 例中 159 通过。
- 死代码：`frontend/src/stores/`（空目录，实际用 `store/`）；git 分支残留 `worktree-agent-aa8a444c27b24c555`、`worktree-agent-ad2d7e0a19e0b1605` + `.claude/worktrees`
- activity_logs 4,796 行无保留策略
- 服务层命名散：tmdb / tmdb_detail / tmdb_cache / tmdb_cache_migration；emby / emby_db / emby_scan / emby_cache_sync / emby_tmdb_update；nf_sync / nf_sync_phases

---

## 4. 优化 Spec

### S1 凭据与日志脱敏（P0，最高优先）

- **现状**：见 P0-1/2/3。
- **目标**：公开仓库内不存在任何可用凭据；日志不含任何密钥。
- **动作**：
  1. **轮换**（凭据已公开，改文件无用）：NextFind Web 密码 → 重新登录取新 cookie；NextFind OpenAPI Key 重新签发；作废涉事 115 分享链接。
  2. **清历史**：**已决策 — 删库重建**（单人单 remote，重建比 `filter-repo` 彻底）。重建后确认 `private` 状态与 `.gitignore` 生效再推。

  3. **防复发**：加 `.githooks/pre-commit` + `make lint-secret`（正则：`password=|api_key=|X-API-Key: ` 后跟 12+ 字符）；`references/*.md` 里的凭据一律替换为 `{api_key}` / `$NF_PASSWORD` 占位并注明取法（`pass show`）。
  4. `services/tmdb.py`: 错误日志只记 `path`，不记 `result`；`core/http_client.py`: 错误 detail 剥离 query string（保留 path）。
  5. `auth_config.json` → 迁入 `platform_configs` 同库或环境变量；登录端点加失败计数 + 指数退避锁定（5 次/5 分钟）。
- **红线**：禁止在任何已跟踪文件中出现真实凭据；禁止把密钥拼进 URL 后落日志；禁止以"内网无所谓"为由跳过轮换。
- **验收**：`git grep -E "***REMOVED***|zv8icxx|api_key=[A-Za-z0-9]{20,}"` 在 HEAD 与全历史均无命中；`grep -rE "api_key=" logs/ | wc -l` = 0；新日志中 TMDB 404 只出现 `/3/tv/317955`。
- **非目标**：本期不做全量日志脱敏框架、不上 WAF。

### S2 迁移机制（P1）— 口径已复定：**不引 alembic**（2026-10-01）

> 原 S2 定的是「引 alembic 为正解」。主人复定：**alembic 没必要**（成本集中在存量库 baseline 对齐，约 2 小时，本场景不划算）。改用「幂等 SQL + 执行台账 + drift 门禁」三件套，落地成本约 10 分钟。**本节为最终口径。**

- **现状（实测，非推断）**：
  - 生产库 `192.168.31.10:5432/unisub` **已执行到 006**：001 两索引在；002 `mp_subscription` 在；003 `tmdb_season` 在；004 `aired_count` 列在；005 `emby_season_cache` 在；006 旧 `api_key=` 直链 **0** 条 / 新签名路径 **3,612** 条。
  - `schema_migration` 表**不存在** → 无台账，"到第几版"只能靠记忆。**这是本项唯一的真缺口。**
  - `migrations/00X_*.sql` 6 文件无人引用（手执行）；001~005 均带 `IF NOT EXISTS`（可重跑）；006 是数据修正且写 **set 终值**（可重跑）。**文件本身是规范的，缺的只是记账。**
  - drift 已实测存在（P1-4），根因见下方动作 5。
- **目标**：① 任一存量库一条命令查出停在第几版；② 任一迁移可重复执行无副作用；③ 空库一条命令得到与模型一致的 schema；④ 模型与库的偏差由门禁发现，不靠人眼。
- **组件边界（真值三分，写死）**：
  - 新库基线 = `Base.metadata`（`models/*.py`）→ `init_db()` 的 `create_all` **保留**，只服务新库
  - 存量库变更 = `migrations/NNN_*.sql`（幂等 + 按序 + 手动执行）
  - 执行台账 = 新表 `schema_migration`（"到第几版"的唯一真值）
  - 门禁 = `backend/scripts/schema_drift_check.py`（本轮已交付并实跑通过）
- **动作**（SQL 可直接复制执行）：
  1. 新增 `migrations/000_schema_migration.sql`：
     ```sql
     -- 迁移台账：唯一的"到第几版"真值。幂等，可重复执行。
     CREATE TABLE IF NOT EXISTS schema_migration (
         version    TEXT PRIMARY KEY,
         applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
         note       TEXT
     );
     INSERT INTO schema_migration(version, note) VALUES ('000_schema_migration', '台账表自身')
     ON CONFLICT (version) DO NOTHING;
     ```
  2. **回填台账**（生产库已到 006，逐版本按事实核实**后**再 stamp，核实 SQL 见 §7.3）：
     ```sql
     INSERT INTO schema_migration(version, note) VALUES
       ('001_add_indexes',                    '回填：2026-10-01 核实已执行'),
       ('002_mp_subscription',                '回填：2026-10-01 核实已执行'),
       ('003_tmdb_season',                    '回填：2026-10-01 核实已执行'),
       ('004_tmdb_season_aired',              '回填：2026-10-01 核实已执行'),
       ('005_emby_season_cache',              '回填：2026-10-01 核实已执行'),
       ('006_strip_emby_image_api_key',       '回填：2026-10-01 核实已执行')
     ON CONFLICT (version) DO NOTHING;
     ```
     ⚠️ `version` 必须**与实际文件名逐字一致**（先 `ls migrations/` 核一遍再执行），否则台账与文件对不上，`make db-status` 会骗人。
  3. 001~006 **每个文件末尾追加自带记账行**：`INSERT INTO schema_migration(version) VALUES ('006_strip_emby_image_api_key') ON CONFLICT (version) DO NOTHING;`
  4. `Makefile` 增 `db-migrate`（`set -e; for f in migrations/[0-9]*.sql; do psql -f "$f"; done`）与 `db-status`（查台账）。
  5. **漂移归位（与 alembic 无关，必须做）**：`emby_cache` 多出的 5 列（`poster_url`/`tmdb_total_eps`/`tmdb_aired_eps`/`tmdb_next_air_date`/`tmdb_poster_path`）是 `tmdb_cache_migration.py:43` 数据搬迁后的**残留**——实测：代码对 5 列的读写**全部指向 `tmdb_cache`**（`tc.` 前缀，`emby_db.py:83` / `completion.py:60-78` / `dashboard.py:44`），`emby_cache` 侧**零引用**；且 `tmdb_cache` 覆盖更全（3,669 行 vs 3,612）。→ 备份后 `DROP COLUMN IF EXISTS`（migration 007），备份表 `emby_cache_bak_20261001` 留 30 天。
  6. drift 门禁接入 `make lint-backend`：非空即失败。
- **接口契约**：
  - `make db-status` → `SELECT version, applied_at FROM schema_migration ORDER BY version;`（6 行 001~006）
  - 文件名 `NNN_snake_case.sql`（三位递增且唯一）；**version 键 = 文件名去 `.sql`**
  - 每条迁移必须：幂等 DDL（`IF NOT EXISTS`/`IF EXISTS`）+ **末尾记账行**
- **数据格式**：`schema_migration(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now(), note TEXT)`
- **量级约束**：6 文件 / 10 表 / 单实例单人维护；台账 < 100 行/年。
- **红线**：
  - 禁止迁移里写增量运算（`SET n = n + 1`）——重跑即错，一律 set 终值
  - 禁止改了模型不写迁移（**新表**可由 `create_all` 承担；**改存量表必须写迁移**）
  - 禁止手工执行迁移后不记账
  - 禁止把 `create_all` 当存量库的升级手段
- **验收**：
  1. `make db-status` 输出 6 行 001~006，`applied_at` = 回填时间
  2. `make db-migrate` **连跑两次**无报错，台账仍 6 行
  3. 空库演练：建临时库 → `create_all` + `make db-migrate` → `schema_drift_check.py` 输出 `DRIFT: (无)` → 删库（**前置：动作 5 已完成**）
  4. `make lint-backend` 含 drift 门禁且当前为绿
- **非目标**：不引 alembic；不做自动生产迁移（仍发版时手动执行 + 校验）；不做 schema diff 自动生成迁移。
- **升级判据（出现任一再考虑 alembic）**：① 迁移需要**回滚**（改列类型/删列/回填失败要退）；② DDL 与数据回填混编且需中途可观测；③ 多人/多环境并行改 schema，台账不足以表达依赖顺序。

### S3 调度器失败退避 + 运行状态持久化（P1）

- **现状**：见 P1-5（10 秒重试风暴，实测）、P2-8（重启即全量）。
- **目标**：任一依赖抖动不得放大成重试风暴；重启不产生额外扫描；失败有上界。
- **动作**：
  1. 时基与结果解耦：进入执行**前**即写入 `last_attempt_at`，执行结果另记 `last_success_at`（失败不重置时基）。
  2. 失败退避：连续失败 n 次 → 下次尝试延后 `min(base * 2**(n-1), ceiling)`（base=间隔，ceiling=30 min），成功后清零 → 这是**降级通道的上界**，必须有。
  3. 循环异常单独计数 + 连续同因异常聚合日志（同样内容 1 分钟内只记 1 行 + 累计次数），治日志风暴。
  4. 状态落库（新表 `scheduler_state`：task / last_attempt_at / last_success_at / fail_streak / updated_at），重启后按 last_success_at 判定是否到期，不再无条件全量。
  5. `scheduler_state.json` 退役（并入 S6）。
- **红线**：**禁止用固定 sleep / 常量延时代替退避计算**；禁止在失败路径不更新时基；禁止无上界的重试。
- **验收**：人为断掉 Emby，10 分钟内 `调度器触发全量扫描` 出现次数 ≤ 2（当前为 60）；恢复后按正常间隔恢复；重启后 5 分钟内无全量扫描触发（除非已过期）；`fail_streak` 可在库中查询统计。
- **非目标**：本期不引 APScheduler/Celery 等外部调度器（单机规模不值得）。

### S4 单实例约束显式化（P2）

- **现状**：见 P2-7。
- **目标**：约束可见、可断言、违反即失败。
- **动作**：① `ARCHITECTURE.md` 新增「部署约束」栏，明写"后端必须单进程单实例；workers 必须 = 1；禁止多副本水平扩展"；② 启动断言：读 `WEB_CONCURRENCY`/`--workers`，`>1` 直接 `sys.exit` 并打错误日志；③ 在 `STANDARDS.md` 增准入条款引用（进程内状态白名单：平台配置快照缓存、调度运行标志、config_store 缓存 —— 每条须注明一致性方案与失效方式）。
- **红线**：禁止未经声明新增进程内缓存；禁止以"加机器扩容"为由提高 worker 数。
- **验收**：`WEB_CONCURRENCY=2` 启动 → 进程退出且日志给出原因；`grep -rn "进程内状态" ARCHITECTURE.md` 可定位白名单。

### S5 扫描与 HTTP 隔离（P2）

- **现状**：见 P2-9。
- **目标**：长时间扫描不阻塞 API 响应。
- **动作**：优先级从低到高——① 扫描内每个分页 `await asyncio.sleep(0)` 让出（低成本）；② `supervisor` 增第二个 program（`unisub_worker`）承接扫描，通过 DB 状态表通信（中成本，推荐）；③ 引入任务队列（不推荐，超规格）。
- **红线**：禁止在事件循环内做 CPU 密集/同步阻塞调用；分页拉取必须有单页上限与总条数保护。
- **验收**：扫描进行中 `curl -w %{time_total} /api/subscriptions` p95 < 1s（当前扫描期间明显抬高）。

### S6 配置持久化收敛（P1）

- **现状**：见 P1-6。
- **动作**：`auto_subscribe_config` / `ai_config` / `auth_config` / `scheduler_state` 迁入 DB（新建 `app_configs` 键值表或各专表），JSON 文件仅作导入来源；`auto_subscribe_history.json`（169 KB）单独评估——历史查询性数据应建表而非整文件读写。迁移需一次性脚本 + 回滚开关。
- **红线**：禁止新增业务配置写 JSON 文件；禁止请求路径内做同步文件 IO。
- **验收**：`app/data/` 仅剩迁移期的 `.bak`；配置修改在多进程下不再自相矛盾（S4 断言通过的前提下）。

### S7 测试隔离（P3，但立刻可修）

- **现状**：见 P3-12，`test_health.py` 直连生产 PG 且稳定 FAIL。
- **动作**：删掉 `test_health.py` 内的本地 `client` fixture，复用 conftest（含 `get_db` override）；或对 `/health` 走显式的 engine 注入。**测试不得触碰生产 DB。**
- **验收**：`uv run pytest -q` 全绿；断网/断 DB 环境下同样全绿。

### S8 文档与死代码（P3）

- **动作**：① 按实测重写 `ARCHITECTURE.md`（去掉 Element Plus/Docker Compose/alembic/旧 router 清单，补 15 router + 40 service + 部署约束 + 状态表）；② `STANDARDS.md:1.3` 给 `models/` 加显式例外条款；③ 删 `frontend/src/stores/`、清理 `worktree-agent-*` 分支与 `.claude/worktrees`；④ `activity_logs` 加保留策略（90 天，调度器每日清理一次）；⑤ 服务层按域重组（照 `auto_subscribe/` 范式：`emby/`、`nf/`、`tmdb/`、`mp/`）。
- **非目标**：本轮不做服务层大重组（⑤ 降级为"新文件按域放入子包"，不强制搬迁存量）。

---

## 5. 排期建议

| 阶段 | 内容 | 阻断条件 |
|---|---|---|
| Phase 0（当天） | S1 轮换 + 清历史 + 日志脱敏 + pre-commit；S7 测试隔离 | 需主人提供新凭据 |
| Phase 1（本周） | S2 **轻量迁移台账**（幂等 SQL + schema_migration + drift 归位）；S3 退避与状态落库 | 空库演练先通过再上生产 |
| Phase 2（下周） | S4 单实例断言；S6 配置入 DB | S2 完成后才有落库路径 |
| Phase 3（结构治理） | S5 隔离；S8 文档重写 / 死代码 / 日志保留 | — |

---

## 6. 非目标（本期明确不做）

- 不重构三层架构（它是对的）
- 不替换 FastAPI / Vue / PostgreSQL 选型
- 不引入 Redis / MQ / Celery（单机规模，进程内缓存 + DB 足够）
- **不引入 alembic**（口径见 S2：台账表 + 幂等 SQL + drift 门禁已足够；alembic 的成本集中在存量库 baseline 对齐，本场景不划算）
- 不做多副本水平扩展（S4 反向冻结这条）
- 不做全量日志脱敏框架、不做 WAF、不做审计合规改造
- 不搬迁存量服务层文件（只约束新增）

---

## 7. 决策记录（2026-10-01，主人已定）

| # | 决策项 | 结论 | 影响 |
|---|--------|------|------|
| 1 | 执行归属 | **交 coder 执行，Architect 出 spec + 持验收权** | 已建 4 张看板任务（见下） |
| 2 | 迁移机制 | ~~alembic~~ → **复定为不引 alembic**：幂等 SQL + `schema_migration` 台账 + drift 门禁（2026-10-01 主人复定：alembic 成本集中在存量库 baseline 对齐约 2h，本场景不划算） | S2 已按新口径重写；drift 归位仍在 Phase 1 |
| 3 | 仓库形态 | **删库重建**（不再保留现有 git 历史） | S1 清历史项改为重建；**凭据轮换仍必须做**（已公开即已泄漏，重建不能撤销泄漏） |

### 7.1 看板任务（assignee = coder，工作目录 = dir:/home/hermes/projects/unisub）

| 任务 | ID | 依赖 |
|------|----|------|
| Phase 0：日志脱敏 + 凭据门禁 + 登录限流 + 测试隔离（S1 代码侧 / S7） | `t_e308f9e6` | ready |
| Phase 1：轻量迁移台账 + drift 归位 + 调度器失败退避（S2 / S3） | `t_a2adace2` | 依赖 Phase 0；✅ 2026-10-01 已同步（标题 + **正文**：正文原写「已定：alembic」，已改为不引，并附空库演练/幂等双跑验收） |
| Phase 2：单实例断言 + 配置入 DB（S4 / S6） | `t_28bd67be` | 依赖 Phase 1 |
| Phase 3：扫描隔离 + 文档重写/死代码清理（S5 / S8） | `t_9bc9a53a` | 依赖 Phase 2 |

### 7.2 主人本人待办（Architect 不代持凭据）

1. NextFind Web 密码改密 → 重新登录取新 cookie；NextFind OpenAPI Key 重新签发
2. 作废涉事 115 分享链接（`password=<已脱敏>`）
3. 删库重建推送（重建后先确认仓库 private 与 `.gitignore` 生效）

### 7.3 迁移现状核实 SQL（本次实测证据，2026-10-01）

台账回填前必须先证明"生产库到底执行到哪一版"，逐版本按事实判定，不靠记忆：

```bash
export PGPASSWORD=$PGPASSWORD   # 从本地 pass / .env 注入，勿写字面值
psql -h 192.168.31.10 -U unisub -d unisub -At -c "
select '01_indexes',            count(*) from pg_indexes where indexname in ('ix_subscriptions_tmdb_id','ix_activity_logs_created_at')
union all select '02_mp_subscription',  count(*) from information_schema.tables  where table_name='mp_subscription'
union all select '03_tmdb_season',      count(*) from information_schema.tables  where table_name='tmdb_season'
union all select '04_aired_count',      count(*) from information_schema.columns where table_name='tmdb_season' and column_name='aired_count'
union all select '05_emby_season_cache',count(*) from information_schema.tables  where table_name='emby_season_cache'
union all select '06_old_unsigned_url', count(*) from emby_cache where emby_image_url like '%api_key=%'
union all select '06_new_signed_path',  count(*) from emby_cache where emby_image_url like '/api/emby/image/%'
union all select 'ledger_table',        count(*) from information_schema.tables  where table_name='schema_migration';
"
```

本次实测输出（全部 1 = 已执行，006 已生效，台账表 0 = 不存在）：

```
01_indexes|2  02_mp_subscription|1  03_tmdb_season|1  04_aired_count|1
05_emby_season_cache|1  06_old_unsigned_url|0  06_new_signed_path|3612  ledger_table|0
```

漂移 5 列的残留判定证据：

```bash
# ① 数据在（不是空列）：poster_url 3385 / tmdb_total_eps 3386 / tmdb_aired_eps 880 / tmdb_next_air_date 193 / tmdb_poster_path 3385，共 3612 行
# ② 代码零引用（全部指向 tmdb_cache）：
grep -rn '\bposter_url\b\|\btmdb_total_eps\b\|\btmdb_aired_eps\b\|\btmdb_next_air_date\b\|\btmdb_poster_path\b' backend/app --include='*.py'
#    命中全部为 schemas/*.py 字段声明、models/tmdb_cache.py、或 tc.xxx 前缀 → emby_cache 侧无读无写
# ③ 数据已在 tmdb_cache（覆盖更全）：tmdb_cache 3669 行，tmdb_total_eps 3669 / poster_url 3664 / tmdb_poster_path 3660 / tmdb_next_air_date 76
#    → 结论：emby_cache 这 5 列是 tmdb_cache_migration.py:43 搬迁后的残留，可删（先备份表）
```

---

## 8. 追加评审：JEV（TypeSafe System One）引入评估

> 追加日期：2026-10-01。结论基于**实测 A/B**，不是推测。

### 8.1 结论

**可以引入，且值得引入 —— 但只在"兜底判定"这一处，绝不做主干匹配。**

JEV 是"代码里的智能 if"（输入 state + 类型化 questions，输出**校准概率**，不生成文本），
正好对上本项目 35% 订阅量所依赖的自动订阅匹配链路里最弱的一环：**没有校准的启发式阈值**。

### 8.2 实测 A/B（`backend/scripts/jev_ab_probe.py`，可复跑）

A 侧 = 直接 import 项目的 `auto_subscribe/pipeline/matching.py`；B 侧 = JEV `noul` + `choice`。

| 案例 | 现有启发式 | JEV（同作品概率 / 选择） |
|---|---|---|
| 海上心狱 vs 海上钢琴师 | 判"足够相似" → **误订** | 0.02 / none → 拒绝 ✓ |
| 实习生(2026) vs 实习生(2015) | 相似 → **误订** | 0.07 / none → 拒绝 ✓ |
| 百分之十：电影版 vs 百分之十(剧) | 相似 → **误订** | 0.04 / none → 拒绝 ✓ |
| 蓦然回首(2026) vs 蓦然回首(2024) | 相似 → **误订** | 0.10 / none → 拒绝 ✓ |
| 一瓯春(2026, tv) 正例 | 采纳 ✓ | 0.97 / cand_1 ✓ |
| 核战边缘(2026, movie) 正例 | 采纳 ✓ | 0.98 / cand_1 ✓ |

- **现有启发式 4/6 错判**（4 个反例全部误订）；**JEV 6/6 正确**
- 分离度：反例 0.02~0.10，正例 0.97~0.98 → 阈值可设得极宽，±0.02 抖动不影响
- 延迟 0.88~0.94s/次（单请求 2 问题）；成本约 $0.00001/次（$0.042/M input，output 免费）

失败模式归因（为什么现有逻辑会错）：
1. `matching.py:96` 中文阈值 `共同汉字≥2 且占比≥30%` —— "海上"+2 字即通过（海上心狱/海上钢琴师）
2. `matching.py:64` 兜底 `_best_by_vote` 取**评分最高**当**最对的** —— 真正条目不在候选里时会返回一个无关但热门的条目，而不是 `None`。这是最危险的一条
3. `matching.py:137` `_strip_season` 剥冒号副标题后精确命中同 IP 的另一个条目（电影版 → 剧版）

### 8.3 接入 spec

- **组件边界**：新增 `services/decision.py`（唯一入口，走 `core/http_client.py`），
  `pipeline/matching.py` 只调用它做校验，**不**承担 HTTP。
  ⚠️ 共享脚本 `~/.hermes/scripts/jev.py` 用**裸 stdlib urllib**，直接搬进项目**违反 STANDARDS 铁律**（HTTP 必须走 `core/http_client.py`），必须重写为走统一封装。
- **接口契约**：
  - 触发时机：**仅当 `pick_best` 精确匹配（阶段 1/2/3）全部失败、进入阶段 4/5 之前**调用。精确匹配是对的、免费的、零延迟的，不该花 JEV 的钱。
  - 入参：`{待订阅: {标题, 年份, 类型}, 搜索结果: [{序号, 标题, 年份, 类型, 评分}]}`
  - 出参：`{same_work: 概率, which: 候选 key, confidence}`
  - 耗时预算：< 2s（实测 0.9s），超时走降级
- **数据格式**：`questions` 用扁平 key（`same_work__0` / `which__0`），`choice.criteria` 必须是 **dict**（list 会 422），`score.criteria` 才是有序 list。
- **量级约束**：JEV 只在 fallback 路径调用 → 调用量 = 冷门/歧义条目数，远小于每日候选量。
  参考：`subscribe` 累计 1191 条，其中**自动订阅 421 条（35%）**；activity_logs 每日 18~74 条。
- **判定规则（代码侧）**：`same_work ≥ 0.7` **且** `which != none` → 采纳；`≤ 0.3` → 拒绝；
  中间区间 → 保留旧启发式结果并记 warn 日志（**双重确认，不叠加两个风险**）。
- **异常降级**：**fail-closed 回退旧启发式**（自动订阅场景绝不能因为 JEV 挂了就随便订），并记 error 日志。
- **非目标（红线）**：
  - **不做算术/计数/日期序**：年份 ±1、年份精确、集数统计一律留在代码里。C4 虽然过了，但那是它识别到"年份不同"这一事实，**不能把数值比较交给它**
  - **不让它生成文本**：`_ai_assisted_search` 的"输出标准化媒体名"部分保留 LLM 或改规则生成；JEV 只做**选择/校验**
  - **不替换 `pick_best` 的精确匹配阶段**（阶段 1/2/3 保留）
  - **不 pin `jev-latest`**：阈值标定完必须 pin 到真实版本号（响应 `model` 字段给出，如 `jev-1.13.0`）
  - **不把标题里的元信息/测试标注塞进 state**：实测教训 —— state 里写"本条为验证分支人工注入"会把 0.93 打成 0.17（字面理解）

### 8.4 前置门槛（上线前必做）

本轮 6 例只是**探针，不是标定**。上线前必须：
1. 从 `activity_logs`（4811 条）导出历史订阅/退订对，构造 jsonl
2. 用 `jev.py map --concurrency 8` 批量回放，与现有 `pick_best` 输出对照，算准确率 / 误订率 / 成本 / 延迟
3. 中文标题需在本项目语料上自测标定（JEV 英文训练为主），阈值按实测调
4. 结论达标才改生产链路，否则只上"影子模式"（记录不生效）

### 8.5 另一个已失效的替代点（实测：已静默退化 8 天）

`pipeline/search.py:105 _ai_assisted_search` 用**生成模型**（`ai_config.json`: `deepseek-flash` @ `192.168.31.10:63000`）做**判定**任务，
再 `_parse_ai_media` 解析 JSON —— 用错了工具：格式异常就丢、不确定度不可得、点对点串行不可批量。

**更严重的是它已经不工作了**（实测日志，带日期）：

| 日期 | AI 识别成功 | AI 调用失败 |
|---|---|---|
| 09-15 ~ 09-21 | 1~11 次/天 | 0 |
| 09-22 | 4 | 6 |
| 09-23 ~ 09-30 | **0** | 7~12 次/天（全是 `503 Service Unavailable`） |

- 连续 **8 天 0 成功**，失败原因单一：`503`
- 期间订阅照常在产出（09-29 仍新增「野兽之心」）→ 说明它**静默降级到了 `pick_best` 启发式**，而**没有任何告警**
- 手工探活（今日）：该端点 `HTTP 200`，模型解析为 `deepseek-v4.1-flash` → 是**间歇性 503**，不是端点死亡

结论有两条，第二条比第一条重要：

1. `_ai_assisted_search` 的"选择/校验"应换 JEV `choice`（从候选里选），"生成标准化候选名"保留 LLM 或改规则生成。
   **重新评估前提：先修 503 的根因或明确放弃这条 LLM 路径。**
2. **降级必须可见。** 这 8 天里系统"看起来正常"，其实精度已掉到无校准阈值水平。
   JEV 接入的降级策略（不论 fail-open 还是 fail-closed）**都必须产出可见信号**（日志 warn/error + 计数），
   否则就是把同一个坑再挖一遍。这条已写入 4A/4B 的验收项。

### 8.6 回放实验的可行性限定（实测）

- **没有候选快照**：10 张表（`activity_logs`/`subscriptions`/…）均不存搜索结果快照；
  日志只记 `[自动订阅] 共获取 N 个条目，开始搜索 TMDB...` 与 `新增订阅: X (tmdb_id=…, 来源=…)`，**不记候选列表**。
- 因此 4A 的回放必须**重建候选集**：对历史自动订阅条目重新执行搜索拿候选。
- 局限必须声明：TMDB 现状 ≠ 当时结果（库已变化）；这使回放结论为**方向性验证**，不是精确复现。
- 已有可用真实样本：`subscribe` 1191 条中自动订阅 **421 条**（35%）；`unsubscribe` 102 条（含 07-21 17:03 同分钟批量退订 4 条的痕迹）。



