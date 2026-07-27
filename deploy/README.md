# UniSub 部署手册

## 架构

```
systemd (发行版 supervisor.service)
  └── supervisord
        ├── unisub:backend  — deploy/start-api.sh → uvicorn  :8002
        └── unisub:frontend — deploy/nginx.conf（独立 nginx）:8082 → 反代 /api 到 :8002
```

- 端口:后端 API `8002`,前端访问入口 `8082`
- 日志:`/home/hermes/projects/unisub/logs/`(supervisor 捕获)+ `backend/logs/`(应用自写)
- 敏感配置:`backend/.env`(已被 gitignore,不入库)

## 前置条件

- Python 3.13+(uv 管理)、Node.js 20+、PostgreSQL(192.168.31.10:5432,数据库 unisub)
- supervisor(`apt install supervisor`,发行版自带 systemd unit)

## 首次部署

```bash
# 1. 建库（需超级用户；应用连接用的是普通用户 unisub，见 .env）
psql -h 192.168.31.10 -U tgbot -c "CREATE DATABASE unisub;"

# 2. 后端依赖
cd /home/hermes/projects/unisub/backend && uv sync

# 3. 环境配置 — 复制模板并填入真实值(尤其是 UNISUB_JWT_SECRET 必须换强随机值)
cp .env.example .env   # .env 已 gitignore

# 4. 前端构建
cd /home/hermes/projects/unisub/frontend && npm ci && npm run build

# 5. 注册 supervisor 子进程
sudo ln -sf /home/hermes/projects/unisub/deploy/supervisor.conf /etc/supervisor/conf.d/unisub.conf
sudo supervisorctl reread && sudo supervisorctl update
sudo supervisorctl status unisub:*
```

访问 `http://<IP>:8082`。

## 环境变量(backend/.env)

| 变量 | 说明 | 默认值 |
|------|------|--------|
| UNISUB_DEBUG | 调试模式 | false |
| UNISUB_DATABASE_URL | 数据库连接 | postgresql+asyncpg://unisub:unisub@192.168.31.10:5432/unisub |
| UNISUB_CORS_ORIGINS | 跨域来源(JSON 数组,整体单引号包裹) | ["http://localhost:5173","http://localhost:3000"] |
| UNISUB_JWT_SECRET | JWT 签名密钥(**生产必须替换**) | unisub-forward-jwt-secret |
| UNISUB_PROXY_URL | 外网代理(访问 TMDB 用,可选) | 无 |

平台凭据(NextFind / MoviePilot / Emby / TMDB 的 URL + API Key)部署后在前端「设置」页配置,存数据库。

## 运维命令

```bash
sudo supervisorctl status unisub:*            # 查看状态
sudo supervisorctl restart unisub:backend     # 重启后端
sudo supervisorctl restart unisub:frontend    # 重启前端 nginx
sudo supervisorctl tail -f unisub:backend     # 实时日志
```

或在项目根目录用 Makefile:`make status` / `make restart-backend` / `make logs`。

日常更新:
- 后端改动 → `cd backend && uv sync && sudo supervisorctl restart unisub:backend`
- 前端改动 → `cd frontend && npm run build`(nginx 直接读静态文件,无需重启)

## 遗留方案清理

本仓库曾使用「systemd 直跑 uvicorn + 主机 nginx 站点」方案(已移除 `unisub-backend.service`、`unisub-nginx.conf`)。
如主机上仍残留旧 unit:

```bash
sudo systemctl disable --now unisub-backend
sudo rm -f /etc/systemd/system/unisub-backend.service
sudo systemctl daemon-reload
```
