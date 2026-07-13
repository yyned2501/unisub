# UniSub — 统一媒体订阅聚合器

## Architecture

FastAPI + Vue 3 + Element Plus + PostgreSQL 的项目，详见 `ARCHITECTURE.md`。

## Technical Stack

- **Python**: 3.13+, uv 管理
- **Backend**: FastAPI + SQLAlchemy async + asyncpg + PostgreSQL
- **Frontend**: Vue 3 + Element Plus + Pinia + Vue Router + Vite
- **External APIs**: NextFind OpenAPI (192.168.31.10:8092), MoviePilot REST API (192.168.31.10:3000)
- **Cache**: Memory cache for platform configs (no Redis)

## Coding Standards

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

### NextFind OpenAPI
```
Base: http://192.168.31.10:8092/api/openapi
Auth: Header X-API-Key: {api_key}

GET  /search?query={keyword}&type={movie|tv}
POST /subscriptions/add    Body: {"tmdb_id": int}
POST /subscriptions/remove Body: {"tmdb_id": int}
GET  /subscriptions
GET  /quota
GET  /history
POST /transfer Body: {"tmdb_id": int, "target_folder": str}
GET  /directories?cid={parent_id}
```

### NextFind Web API (for missing episodes)
```
Base: https://nf.js.248226785.xyz:8443
Auth: nextmedia_session cookie (via POST login)

POST /login Body: username=yangyang&password=yy920120
GET  /api/discover?type=全部&sort=更新&region=全部&year=全部&genre=全部&status=缺失集&channel=全部&page=1&page_size=400
```
Returns NDJSON: type=initial (basic data), type=update (detailed data with fillable_episodes), type=done

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
│   │   │   └── activity_log.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── platform.py
│   │   │   ├── subscription.py
│   │   │   ├── search.py
│   │   │   └── dashboard.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── nextfind.py
│   │   │   ├── moviepilot.py
│   │   │   └── orchestrator.py
│   │   └── routers/
│   │       ├── __init__.py
│   │       ├── platforms.py
│   │       ├── search.py
│   │       ├── subscriptions.py
│   │       ├── dashboard.py
│   │       └── tasks.py
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.vue
│   │   ├── main.js
│   │   ├── api/
│   │   ├── router/
│   │   ├── stores/
│   │   ├── views/
│   │   └── components/
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
```

## Verification
1. `uv run python3 -c "from app import ..."` — verify imports work
2. `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000` — verify server starts
3. `curl http://localhost:8000/api/platforms` — returns [] (empty list)
4. test NextFind connection with configured API key