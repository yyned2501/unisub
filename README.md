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

- Python 3.13+（uv 管理）
- Node.js 20+
- PostgreSQL（默认连接 192.168.31.10:5432）
- supervisor（生产，systemd 发行版自带）

### 部署

完整步骤见 [`deploy/README.md`](deploy/README.md)，摘要：

```bash
# 1. 克隆
git clone https://github.com/yyned2501/unisub.git
cd unisub

# 2. 配置环境变量（backend/.env 已 gitignore）
cp backend/.env.example backend/.env
# 编辑 backend/.env 填写数据库连接和平台密钥

# 3. 依赖 + 构建
cd backend && uv sync && cd ..
cd frontend && npm ci && npm run build && cd ..

# 4. 注册 supervisor 子进程
sudo ln -sf "$PWD/deploy/supervisor.conf" /etc/supervisor/conf.d/unisub.conf
sudo supervisorctl reread && sudo supervisorctl update
```

部署后访问 `http://<IP>:8082`（nginx 入口，`/api/` 反代到后端 `:8002`）。

### 开发

```bash
# 后端（8002，先加载 backend/.env）
cd backend
uv sync
set -a && . ./.env && set +a
uv run uvicorn app.main:app --reload --port 8002

# 前端（9527，/api 代理到 localhost:8002）
cd frontend
npm install
npm run dev
```

## 配置

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| UNISUB_DEBUG | 调试模式 | false |
| UNISUB_DATABASE_URL | 数据库连接 | postgresql+asyncpg://unisub:unisub@192.168.31.10:5432/unisub |
| UNISUB_CORS_ORIGINS | 允许的跨域来源 | ["http://localhost:5173","http://localhost:3000"] |
| UNISUB_JWT_SECRET | JWT 签名密钥（未配置则每次启动随机生成） | — |
| UNISUB_FORWARD_USERNAME / UNISUB_FORWARD_PASSWORD | Forward API 登录账号 | — |

### 平台配置（通过 UI）

部署后访问 `http://<IP>:8082`，进入「设置」页面添加平台配置：

- **NextFind**: URL + API Key（X-API-Key 鉴权）
- **MoviePilot**: URL + API Token（Bearer Token 鉴权）

## 技术栈

- **后端**: FastAPI + SQLAlchemy async + asyncpg + PostgreSQL
- **前端**: Vue 3 + Naive UI + Pinia + Vue Router + Vite + UnoCSS
- **部署**: systemd → supervisord → uvicorn `:8002` + nginx `:8082`