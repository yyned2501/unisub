# UniSub 源码部署手册

## 前置条件
- Python 3.13+（uv 管理）
- Node.js 20+
- Nginx
- PostgreSQL（192.168.31.10:5432，数据库 unisub）

## 步骤

### 1. 建库
```bash
psql -h 192.168.31.10 -U tgbot -c "CREATE DATABASE unisub;"
```

### 2. 后端

```bash
cd /home/hermes/projects/unisub/backend
uv sync

# 测试启动
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# 注册 systemd 服务
sudo cp /home/hermes/projects/unisub/deploy/unisub-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable unisub-backend
sudo systemctl start unisub-backend
sudo systemctl status unisub-backend
```

### 3. 前端

```bash
cd /home/hermes/projects/unisub/frontend
npm install
npm run build

# 部署 Nginx 配置
sudo cp /home/hermes/projects/unisub/deploy/unisub-nginx.conf /etc/nginx/sites-available/unisub
sudo ln -sf /etc/nginx/sites-available/unisub /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 4. 访问
打开浏览器访问 `http://<IP>`（默认 80 端口）

## 配置

### 后端环境变量
编辑 `backend/.env` 或 systemd service 中的 Environment 行：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| UNISUB_DEBUG | 调试模式 | false |
| UNISUB_DATABASE_URL | 数据库连接 | postgresql+asyncpg://tgbot:tgbot@192.168.31.10:5432/unisub |
| UNISUB_CORS_ORIGINS | 跨域来源 | ["http://localhost:5173"] |

### 平台配置
部署后访问前端 → 设置页面，添加 NextFind 和 MoviePilot 的 URL + API Key。

## 运维命令

```bash
# 查看后端状态
sudo systemctl status unisub-backend

# 查看日志
sudo journalctl -u unisub-backend -f
tail -f /home/hermes/projects/unisub/backend/logs/unisub_*.log

# 重启后端
sudo systemctl restart unisub-backend

# 重新构建前端
cd /home/hermes/projects/unisub/frontend && npm run build
```