# UniSub — 统一媒体订阅聚合器

## Architecture

FastAPI + Vue 3 + Naive UI + PostgreSQL 的项目，详见 `ARCHITECTURE.md`。

## Technical Stack

- **Python**: 3.13+, uv 管理
- **Backend**: FastAPI + SQLAlchemy async + asyncpg + PostgreSQL
- **Frontend**: Vue 3 + TypeScript + Naive UI + Pinia + Vue Router + Vite + UnoCSS
- **External APIs**: NextFind OpenAPI (192.168.31.10:8092), MoviePilot REST API (192.168.31.10:3000)
- **Cache**: Memory cache for platform configs (no Redis)

## Coding Standards

> **所有后端修改必须遵守 `backend/app/STANDARDS.md`**（含架构铁律、三层解耦、Python 规范、外部 API 对接规则）。
> **所有前端修改必须遵守 `frontend/STANDARDS.md`**（TypeScript 约定、通用抽象层、组件规范、目录结构、路由/API 约定）。
> 本文档只列摘要，完整规范以对应文件为准。

### Python
- 严格三层解耦：routers → services → core/ (第三方库隔离)
- 所有函数/方法必须有类型注解
- 公共函数必须有中文 docstring
- 单文件 <300 行，超过拆模块
- logger 替代 print
- 配置通过 dataclass `parse_config()` 类型安全读取

### Core Layer Conventions
- `core/database.py` — SQLAlchemy async engine + session factory
- `core/http_client.py` — httpx.AsyncClient 封装
- `core/logger.py` — logging 封装，日志输出到文件 + 控制台
- 所有第三方库（sqlalchemy, asyncpg, httpx）只能在 core/ 层导入

### Model Naming
- SQLAlchemy models: 单数形式 (platform_config, subscription, activity_log)
- Pydantic schemas: 复数形式 + 用途后缀 (PlatformConfigCreate, SubscriptionResponse)

### Router Naming
- 每个 router 对应一个功能模块
- 使用 APIRouter(prefix="/api/...", tags=["..."])
- 统一错误处理：HTTPException 带中文 message

### 数据库
- SQLAlchemy async ORM + asyncpg
- 迁移用 alembic（初始用 create_all）
- 连接字符串从 config 读取
- 应用连接用户（backend/.env）: `postgresql+asyncpg://unisub:unisub@192.168.31.10:5432/unisub`
- 两个数据库用户：
  - `unisub`（普通用户）— 应用连接用，对所有业务表有完整 CRUD + public schema CREATE 权限
  - `tgbot`（超级用户）— 仅用于建库等管理操作（`CREATE DATABASE` 需超级用户）
- ⚠️ config.py 的默认连接串是 unisub；若手动 `uv run` 调试时未 source backend/.env，
  会用默认值连成 unisub，与生产一致。验证数据库相关逻辑前先 `set -a && source backend/.env && set +a`。

## External API Details

### NextFind API

> ⚠️ 详细文档（含所有端点实测、参数坑、缺集逻辑）见：
> **`backend/app/references/nextfind-api-v2.md`**

OpenAPI 基础：
```
Base:  http://192.168.31.10:8092/api/openapi
Auth:  Header X-API-Key: {api_key}
```
Web API（本地库详情/缺集）：
```
Base:  https://nf.js.248226785.xyz:8443
Auth:  Cookie nextmedia_session (POST /login → username=yangyang&password=***REMOVED***)
```

### MoviePilot REST API
```
Base: {configured_url} (default: http://192.168.31.10:3000)
Auth: Header Authorization: Bearer {api_token} or X-API-Key

POST /api/v1/search/media  Body: {"tmdbid": int, "media_type": "movie"|"tv"}
GET  /api/v1/site/statistic
GET  /api/v1/subscribe/
```
Note: MoviePilot returns 307 redirects on API calls — always follow with -L or allow_redirects=True.

## Project Structure
```
/home/hermes/projects/unisub/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── database.py
│   │   │   ├── http_client.py
│   │   │   └── logger.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── platform_config.py
│   │   │   ├── subscription.py
│   │   │   ├── activity_log.py
│   │   │   ├── emby_cache.py
│   │   │   └── emby_blacklist.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── platform.py
│   │   │   ├── subscription.py
│   │   │   ├── search.py
│   │   │   ├── dashboard.py
│   │   │   ├── emby.py
│   │   │   └── emby_cache.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── nextfind.py
│   │   │   ├── nextfind_admin.py
│   │   │   ├── moviepilot.py
│   │   │   ├── orchestrator.py
│   │   │   ├── tmdb.py
│   │   │   ├── emby.py
│   │   │   ├── emby_scan.py
│   │   │   ├── emby_db.py
│   │   │   ├── subscription.py
│   │   │   ├── dashboard.py
│   │   │   ├── platform.py
│   │   │   └── scheduler.py
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── platforms.py
│   │   │   ├── search.py
│   │   │   ├── subscriptions.py
│   │   │   ├── dashboard.py
│   │   │   ├── emby.py
│   │   │   └── tasks.py
│   │   └── references/
│   │       └── nextfind-api-v2.md
│   ├── migrations/                # 存量库手工迁移 SQL（无 alembic）
│   ├── tests/                     # pytest 测试（sqlite 内存库）
│   ├── pyproject.toml
│   └── .env.example               # 复制为 .env（gitignore）填入真实配置
├── frontend/
│   ├── src/
│   │   ├── App.vue               # 入口页面（含侧边栏 + 导航栏 + 布局）
│   │   ├── main.ts
│   │   ├── env.d.ts              # 全局类型声明
│   │   ├── plugins/               # 插件初始化
│   │   │   ├── assets.ts
│   │   │   └── index.ts
│   │   ├── router/
│   │   │   └── index.ts
│   │   ├── service/               # API 层（响应已解包，返回业务数据）
│   │   │   ├── request.ts         # Axios 实例 + http 客户端
│   │   │   └── api/*.ts           # 每个后端 router 一个文件
│   │   ├── store/                 # Pinia 仓库
│   │   │   └── modules/*.ts
│   │   ├── composables/           # 业务逻辑 + 通用 composable
│   │   │   ├── useAction.ts       # loading 包装
│   │   │   ├── usePolling.ts      # 轮询（自动清理）
│   │   │   ├── useIdSet.ts        # 行级 loading 集合
│   │   │   └── use*.ts            # 各页面业务逻辑
│   │   ├── utils/
│   │   │   ├── message.ts         # msg + confirmDialog
│   │   │   └── format.ts
│   │   ├── types/                 # 领域类型（镜像后端 schemas）
│   │   ├── components/            # 可复用组件
│   │   ├── views/                 # 页面组件
│   │   └── styles/
│   │       └── css/
│   │           └── reset.css
│   └── nginx.conf
├── deploy/                        # 部署配置（systemd → supervisor 架构）
│   ├── README.md                  # 部署手册
│   ├── supervisor.conf            # supervisor 子进程（backend + nginx）
│   ├── nginx.conf                 # 独立 nginx（:8082 反代 /api → :8002）
│   └── start-api.sh               # 后端启动脚本（source backend/.env）
├── Makefile                       # 统一命令入口（dev/lint/test/build/运维）
├── .gitignore
├── .env.example
├── ARCHITECTURE.md
├── README.md
└── STANDARDS.md
```

## Database Schema

### platform_configs
- id: UUID PK
- name: str (unique, "nextfind" | "moviepilot")
- base_url: str
- api_key: str (encrypted or plain — for now plain is OK)
- enabled: bool (default true)
- created_at: datetime
- updated_at: datetime

### subscriptions
- id: UUID PK
- tmdb_id: int
- media_type: str ("movie" | "tv")
- title: str
- poster_url: str (nullable)
- year: int (nullable)
- nf_subscribed: bool (default false)
- nf_status: str (nullable, "active" | "missing_fill" | "completed")
- nf_missing_eps: int (default 0)
- nf_sub_id: str (nullable, NF subscription ID)
- completed: bool (default false)
- created_at: datetime
- updated_at: datetime

### activity_logs
- id: UUID PK
- action: str ("subscribe" | "unsubscribe" | "mp_search" | "mp_downloaded" | "system" | "sync")
- tmdb_id: int (nullable)
- message: str
- created_at: datetime

## API Endpoints (Backend only)
```
GET    /api/platforms
POST   /api/platforms
PUT    /api/platforms/{id}
DELETE /api/platforms/{id}
POST   /api/platforms/{id}/test

GET    /api/search?q={keyword}&type={movie|tv}

GET    /api/subscriptions
POST   /api/subscriptions
DELETE /api/subscriptions/{id}
GET    /api/subscriptions/{id}
POST   /api/subscriptions/sync

GET    /api/dashboard/stats
GET    /api/dashboard/platforms
GET    /api/dashboard/activities
GET    /api/dashboard/nextfind-quota

GET    /api/tasks/status
POST   /api/tasks/trigger
PUT    /api/tasks/config

GET    /api/emby/library
```

## Verification
1. `uv run python3 -c "from app import ..."` — verify imports work
2. `uv run uvicorn app.main:app --host 0.0.0.0 --port 8002` — verify server starts
3. `curl http://localhost:8002/api/platforms` — returns [] (empty list)
4. test NextFind connection with configured API key
5. **Frontend** → `cd frontend && npm run build` — build 通过

## Deployment

架构: systemd（发行版 supervisor.service）→ supervisord → `unisub:unisub_backend`(uvicorn :8002) + `unisub:unisub_frontend`(nginx :8082)。
敏感配置在 `backend/.env`（gitignore），详见 `deploy/README.md`。

After any code change:
- **Frontend changed** → `cd frontend && npm run build && sudo supervisorctl restart unisub:unisub_frontend`
- **Backend changed** → `sudo supervisorctl restart unisub:unisub_backend`
- After restart, wait 3s then verify: `sleep 3 && curl http://localhost:8002/api/platforms`

## 能力唯一化 —— 写新函数前先搜（防重复实现铁律）

同一个能力只允许有一个实现。AI 最容易犯的错不是写错，而是**忘了已经有人写过**：生成是上下文局部最优，写出第二份时没有任何东西会报错。本机项目群实测已出现同一功能 2–4 份不同签名的实现（`login` 两份分别返回 `tuple[bool,str,dict|None]` 与 `tuple[bool,str,str]`；`is_banned` 一份带缓存一份不带），改一处漏一处。

**写任何新函数前，先搜（按能力词搜，不按变量名）：**

```bash
rg -n "(def|async def) .{0,24}(fetch|request|login|parse|merge|send|download|update|notify)" --type py
rg -n "httpx\.|requests\.|aiohttp|sqlite3\.connect|create_engine" --type py   # 是否已有统一封装
rg -n "def <你要写的函数名>" --glob '!tests/**'                                  # 同名函数是否已存在
```

**判定：**

- **命中 → 复用**：需要变体就给原函数加参数 / 加分支，**不要复制改两行另开一份**
- **未命中 → 新建**：建完在本文件「能力表」补一行
- 要改原函数签名 → 先 `rg -n "<函数名>"` 找齐全部调用方，一次改完

**硬性规则：**

- 一个能力 = 一个模块里的一个函数；同名函数全项目只允许一份（测试桩 / 夹具除外，且须带 `_test` / `fake_` 前缀）
- 第三方库只在封装层 import：HTTP / 时间 / 日志 / JSON 一律走封装，禁裸 `httpx.AsyncClient(`、`requests.`、`time.sleep`、`print`
- **一个概念全项目用一个词**：`get` / `fetch` / `load` 只留一个；`user` 不要又写成 `member` / `account`。名字飘了搜索就命中不了，必然重造
- 新增 / 改名 / 删除公共函数，同步更新下表

**收尾自检（提交前）：** 本次新增了几个函数，就逐个问一遍「项目里已有同职责的实现吗」。有 → 合并，不留第二份。

**能力表（本项目唯一入口）**

| 能力 | 唯一入口 | 禁止写法 |
|---|---|---|
| HTTP 请求 | `backend/app/core/http_client.py:AsyncHttpClient` | 裸 httpx |
| CD2 / gRPC | `backend/app/core/clouddrive_client.py:CloudDriveClient` | 裸 gRPC stub |
| DB / 日志 | `backend/app/core/database.py`、`core/logger.py` | 自建引擎 / print |
| 前端接口调用 | `frontend/src/service/api/*` | 裸 axios |
