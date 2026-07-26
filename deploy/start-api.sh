#!/bin/bash
# UniSub API 启动脚本 — 由 Supervisor 调用
# 敏感配置统一从 gitignore 的 backend/.env 读取，不在脚本内硬编码

set -a
source /home/hermes/projects/unisub/backend/.env
set +a

export PYTHONPATH="/home/hermes/projects/unisub/backend"

exec /home/hermes/.local/bin/uv run uvicorn app.main:app --host 0.0.0.0 --port 8002
