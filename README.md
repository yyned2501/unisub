# UniSub — 统一媒体订阅聚合器

> 在 NextFind + MoviePilot 之上建一层订阅管理层，统一搜索、统一管理订阅、定时触发 MP 做搜索补充。

## 功能

- **🔍 统一搜索** — TMDB 搜索，同时查看在 NextFind 的订阅状态
- **📋 订阅管理** — 添加/取消/查看所有订阅，聚合显示进度
- **⚡ 自动化编排** — 订阅后自动同步到 NextFind，定时检查缺集
- **🔄 MP 补充** — 缺集时自动调用 MoviePilot 搜索补充
- **📊 状态看板** — NextFind 额度、平台状态、活动日志

## 数据流

```
用户搜索 → 选择资源 → 点「订阅」
    ↓
NextFind 添加订阅（主力：自动搜索+转存+追更）
    ↓
定时任务轮询 NF 缺集状态
    ↓ 发现缺集
调用 MP 搜索 API（下载引擎）
    ↓ 下载完成
NF 转存入库 → 状态更新
```

## 快速开始

### 环境要求

- Docker & Docker Compose
- PostgreSQL 数据库（默认连接 192.168.31.10:5432）

### 部署

```bash
# 1. 克隆
git clone https://github.com/yyned2501/unisub.git
cd unisub

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填写你的数据库连接和平台密钥

# 3. 启动
docker compose up -d
```

### 开发

```bash
# 后端
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev
```

## 配置

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| UNISUB_DEBUG | 调试模式 | false |
| UNISUB_DATABASE_URL | 数据库连接 | postgresql+asyncpg://tgbot:tgbot@192.168.31.10:5432/unisub |
| UNISUB_CORS_ORIGINS | 允许的跨域来源 | ["http://localhost:5173","http://localhost:3000"] |

### 平台配置（通过 UI）

部署后访问 `http://<IP>:3001`，进入「设置」页面添加平台配置：

- **NextFind**: URL + API Key（X-API-Key 鉴权）
- **MoviePilot**: URL + API Token（Bearer Token 鉴权）

## 技术栈

- **后端**: FastAPI + SQLAlchemy async + asyncpg + PostgreSQL
- **前端**: Vue 3 + Element Plus + Pinia + Vue Router + Vite
- **部署**: Docker Compose（Nginx + Uvicorn）