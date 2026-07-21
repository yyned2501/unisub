# UniSub — 统一媒体订阅聚合器

## Architecture

FastAPI + Vue 3 + Naive UI + PostgreSQL 的项目，详见 `ARCHITECTURE.md`。

## Technical Stack

- **Python**: 3.13+, uv 管理
- **Backend**: FastAPI + SQLAlchemy async + asyncpg + PostgreSQL
- **Frontend**: Vue 3 + Naive UI + Pinia + Vue Router + Vite + UnoCSS
- **External APIs**: NextFind OpenAPI (192.168.31.10:8092), MoviePilot REST API (192.168.31.10:3000)
- **Cache**: Memory cache for platform configs (no Redis)

## Coding Standards

> **所有后端修改必须遵守 `backend/app/STANDARDS.md`**（含架构铁律、三层解耦、Python 规范、外部 API 对接规则）。
> **所有前端修改必须遵守 `frontend/STANDARDS.md`**（含组件规范、目录结构、路由/API 约定）。
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
- Database URL: postgresql+asyncpg://tgbot:tgbot@192.168.31.10:5432/unisub (可配置)

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
Auth:  Cookie nextmedia_session (POST /login → username=yangyang&password=yy920120)
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
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.vue               # 入口页面（含侧边栏 + 导航栏 + 布局）
│   │   ├── main.js
│   │   ├── plugins/               # 插件初始化
│   │   │   ├── assets.ts
│   │   │   └── index.ts
│   │   ├── router/
│   │   │   └── index.js
│   │   ├── service/               # API 层
│   │   │   ├── request.js         # Axios 实例
│   │   │   └── api/
│   │   │       ├── dashboard.js
│   │   │       ├── emby.js
│   │   │       ├── platforms.js
│   │   │       ├── search.js
│   │   │       ├── subscriptions.js
│   │   │       └── tasks.js
│   │   ├── store/                 # Pinia 仓库
│   │   │   └── modules/
│   │   │       ├── app.js
│   │   │       └── theme.js
│   │   ├── components/            # 可复用组件
│   │   │   ├── common/
│   │   │   │   └── app-provider.vue
│   │   │   ├── MediaCard.vue
│   │   │   ├── PlatformStatus.vue
│   │   │   ├── StatusBadge.vue
│   │   │   └── SubDialog.vue
│   │   ├── views/                 # 页面组件
│   │   │   ├── DashboardView.vue
│   │   │   ├── SearchView.vue
│   │   │   ├── SubscriptionsView.vue
│   │   │   └── settings/
│   │   │       ├── PlatformSettings.vue
│   │   │       ├── TaskSettings.vue
│   │   │       └── EmbyAnalysis.vue
│   │   └── styles/
│   │       └── css/
│   │           └── reset.css
│   ├── Dockerfile
│   └── nginx.conf
├── docker-compose.yml
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
2. `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000` — verify server starts
3. `curl http://localhost:8000/api/platforms` — returns [] (empty list)
4. test NextFind connection with configured API key

## Deployment

After any code change:
- **Frontend changed** → `cd frontend && npm run build`
- **Backend changed** → `sudo systemctl restart unisub-backend`
- After restart, wait 3s then verify: `sleep 3 && curl http://localhost:8002/api/platforms`