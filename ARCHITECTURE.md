# UniSub — 统一媒体订阅聚合器

> 在 NextFind + MoviePilot 之上建一层订阅管理层，统一搜索、统一管理订阅、定时触发 MP 做搜索补充。

## 定位

- **UniSub 是订阅决策层** — 用户在此搜索、添加、管理订阅
- **NextFind 是主力执行层** — 负责自动搜索资源 + 转存到网盘 + 追更
- **MoviePilot 是兜底补充层** — 仅由定时任务触发搜索 API，不做订阅管理
- **不取代任何平台**，只做"指挥+聚合"

## 数据流

```
用户操作：
  [搜索 TMDB] → [选择资源] → [点「订阅」]
                                │
                     ┌──────────┴──────────┐
                     ▼                     ▼
          NextFind 添加订阅           记录到 UniSub 本地库
          （主力：自动搜索+转存）        （聚合状态跟踪）
                     │
                     ▼
          ┌──────────────────────┐
          │ 定时任务：轮询 NF 订阅 │
          │ 检查缺集状态          │
          └──────────┬───────────┘
                     │
           发现缺集 / 无法下载？
                     │
                ┌────┴────┐
                ▼         ▼
              是          否 → 无事发生
                │
                ▼
     调用 MP 搜索 API（搜索种子→下载）
                │
                ▼
     下载完成 → NF 转存入库
                │
                ▼
     UniSub 状态更新（缺集数减少/已入库）
```

## 功能模块

### 1️⃣ 平台配置管理

- 配置 NextFind 地址 + API Key
- 配置 MoviePilot 地址 + API Token
- 连接测试按钮（验证连通性）
- 配置持久化到数据库

### 2️⃣ 统一搜索

- TMDB 搜索（调 NextFind `/api/openapi/search`）
- 搜索结果展示：海报、标题、类型、年份
- 每项标注在两个平台的已有状态（已订阅/已入库/缺集数）
- 一键「订阅」按钮

### 3️⃣ 订阅管理

- 展示所有订阅列表（数据来源：UniSub 本地库 + NextFind 订阅状态聚合）
- 每项展示：标题、类型、当前进度（已下载/N集）、缺集数、来源平台状态
- 操作：取消订阅、刷新状态
- 筛选：电影/剧集、全部/缺集中/已完成

### 4️⃣ 定时编排任务

- **轮询频率**：每 30 分钟检查一次
- **逻辑**：
  1. 查询 NextFind 所有活跃订阅的缺集状态
  2. 对缺集数 > 0 的条目，调用 MP 搜索 API 搜索资源
  3. 记录每次触发结果到活动日志
  4. 避免重复触发（同一条目缺集未变就不重复搜）
- **配置项**：轮询间隔、是否启用 MP 补充

### 5️⃣ 状态看板

- NextFind 积分/额度
- MoviePilot 站点状态
- 订阅统计（总数、缺集数、已完结数）
- 最近活动日志（谁订阅了什么、MP 补充了什么）

## 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 后端 | FastAPI + SQLAlchemy async + asyncpg | Python 3.13+，三层解耦 |
| 前端 | Vue 3 + Element Plus + Pinia + Vue Router | Vite 构建 |
| 数据库 | PostgreSQL（新建 `unisub` 库） | 192.168.31.10:5432 |
| 部署 | Docker Compose（后端 + 前端 + Nginx） | Tower 服务器 |
| 外部依赖 | NextFind OpenAPI + MoviePilot REST API | 局域网直连 |

## 项目结构

```
unisub/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                  # FastAPI 入口
│   │   ├── config.py                # 配置 dataclass
│   │   ├── database.py              # SQLAlchemy async 引擎
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── platform_config.py   # 平台配置表
│   │   │   ├── subscription.py      # 订阅记录表
│   │   │   └── activity_log.py      # 活动日志表
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── platform.py
│   │   │   ├── subscription.py
│   │   │   ├── search.py
│   │   │   └── dashboard.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── nextfind.py          # NextFind API 封装
│   │   │   ├── moviepilot.py        # MoviePilot API 封装
│   │   │   └── orchestrator.py      # 编排逻辑（订阅+定时任务）
│   │   └── routers/
│   │       ├── __init__.py
│   │       ├── platforms.py         # 平台配置 CRUD
│   │       ├── search.py            # 搜索
│   │       ├── subscriptions.py     # 订阅管理
│   │       ├── dashboard.py         # 看板
│   │       └── tasks.py             # 定时任务管理
│   ├── alembic/                     # 数据库迁移
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── App.vue
│   │   ├── main.js
│   │   ├── api/                     # API 调用封装
│   │   │   ├── platforms.js
│   │   │   ├── search.js
│   │   │   ├── subscriptions.js
│   │   │   └── dashboard.js
│   │   ├── router/
│   │   │   └── index.js
│   │   ├── stores/
│   │   │   └── app.js               # Pinia 全局状态
│   │   ├── views/
│   │   │   ├── DashboardView.vue    # 看板
│   │   │   ├── SearchView.vue       # 搜索
│   │   │   ├── SubscriptionsView.vue # 订阅管理
│   │   │   └── SettingsView.vue     # 平台配置
│   │   └── components/
│   │       ├── MediaCard.vue        # 媒体卡片
│   │       ├── StatusBadge.vue      # 状态标签
│   │       ├── SubDialog.vue        # 订阅弹窗
│   │       └── PlatformStatus.vue   # 平台状态组件
│   ├── Dockerfile
│   └── nginx.conf                   # 开发代理 + 生产反向代理
├── docker-compose.yml               # 编排文件
├── .env.example                     # 环境变量模板
├── .gitignore
└── README.md
```

## 数据库模型

### platform_configs

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| name | str | 平台名（nextfind / moviepilot） |
| base_url | str | API 地址 |
| api_key | str | 鉴权密钥 |
| enabled | bool | 是否启用 |
| created_at | datetime | |
| updated_at | datetime | |

### subscriptions

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| tmdb_id | int | TMDB ID |
| media_type | str | movie / tv |
| title | str | 媒体标题 |
| poster_url | str | 海报 URL |
| year | int | 年份 |
| nf_subscribed | bool | 是否已添加到 NextFind 订阅 |
| nf_status | str | NF 端状态（active/missing_fill/completed） |
| nf_missing_eps | int | NF 缺集数 |
| nf_sub_id | str | NF 订阅 ID |
| completed | bool | 是否已完成 |
| created_at | datetime | |
| updated_at | datetime | |

### activity_logs

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| action | str | subscribe / unsubscribe / mp_search / mp_downloaded / system |
| tmdb_id | int | 关联媒体 |
| message | str | 日志内容 |
| created_at | datetime | |

## API 设计

### 平台配置

```
GET    /api/platforms              # 获取所有平台配置
POST   /api/platforms              # 添加平台配置
PUT    /api/platforms/{id}         # 更新平台配置
DELETE /api/platforms/{id}         # 删除平台配置
POST   /api/platforms/{id}/test   # 测试连接
```

### 搜索

```
GET    /api/search?q={keyword}&type={movie|tv}  # TMDB 搜索
```

### 订阅

```
GET    /api/subscriptions              # 订阅列表
POST   /api/subscriptions              # 添加订阅（→ NF + 本地记录）
DELETE /api/subscriptions/{id}         # 取消订阅（→ NF + 清理本地）
GET    /api/subscriptions/{id}         # 订阅详情
POST   /api/subscriptions/sync         # 手动同步订阅状态
```

### 看板

```
GET    /api/dashboard/stats            # 订阅统计
GET    /api/dashboard/platforms        # 平台状态
GET    /api/dashboard/activities       # 最近活动
GET    /api/dashboard/nextfind-quota   # NF 额度
```

### 定时任务

```
GET    /api/tasks/status               # 定时任务状态
POST   /api/tasks/trigger              # 手动触发一次编排
PUT    /api/tasks/config               # 更新定时任务配置
```

## 对接外部 API

### NextFind（OpenAPI，端口 8092）

| 用途 | 端点 | 说明 |
|------|------|------|
| TMDB 搜索 | `GET /api/openapi/search` | query, type |
| 添加订阅 | `POST /api/openapi/subscriptions/add` | tmdb_id |
| 取消订阅 | `POST /api/openapi/subscriptions/remove` | tmdb_id |
| 订阅列表 | `GET /api/openapi/subscriptions` | |
| 缺集诊断 | `GET /api/discover`（Web API） | 需 cookie 登录 |
| 查额度 | `GET /api/openapi/quota` | |
| 转存历史 | `GET /api/openapi/history` | |
| 一键转存 | `POST /api/openapi/transfer` | tmdb_id, target_folder |

鉴权：Header `X-API-Key: <key>`

### MoviePilot（REST API，端口 3000）

| 用途 | 端点 | 说明 |
|------|------|------|
| 搜索资源 | `POST /api/v1/search/media` | tmdb_id, media_type |
| 站点状态 | `GET /api/v1/site/statistic` | |
| 下载状态 | `GET /api/v1/download/M3jxRR` | 待确认实际端点 |

鉴权：Header `Authorization: Bearer <api_token>` 或 `X-API-Key`，需对接时确认

## 部署

```bash
# Tower 上执行
git clone https://github.com/yyned2501/unisub.git
cd unisub
cp .env.example .env
# 编辑 .env 填写配置
docker compose up -d
```

## 开发

```bash
# 后端
cd backend
uv sync
uv run python3 -m app.main

# 前端
cd frontend
npm install
npm run dev
```

## 开发原则

- 严格遵循 Yy 的 Python 项目架构标准（三层解耦、类型注解、中文 docstring、<300行/文件）
- 前端使用 Element Plus 组件库，保持风格统一
- API 错误统一处理，前端统一展示
- 定时任务使用 FastAPI 的 BackgroundTasks + asyncio 实现，不依赖外部调度器
- 配置项可运行时修改，无需重启