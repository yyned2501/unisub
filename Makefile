# UniSub 统一命令入口
# 用法: make <target>
# 生产架构: systemd → supervisord → unisub:backend(uvicorn:8002) + unisub:frontend(nginx:8082)

.PHONY: help setup dev-backend dev-frontend lint lint-backend lint-frontend \
	test test-backend test-frontend build clean \
	status restart restart-backend restart-frontend logs

help: ## 显示所有可用命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: ## 一键初始化（安装前后端依赖）
	cd backend && uv sync --group dev
	cd frontend && npm ci

dev-backend: ## 启动后端开发服务器（自动加载 backend/.env，端口 8002）
	cd backend && if [ -f .env ]; then set -a && . ./.env && set +a; fi && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8002

dev-frontend: ## 启动前端开发服务器
	cd frontend && npm run dev

lint: lint-backend lint-frontend ## 运行全部 lint 检查

lint-backend: ## 后端 lint（ruff + 架构分层）
	cd backend && uv run ruff check .
	cd backend && uv run ruff format --check .
	cd backend && uv run lint-imports

lint-frontend: ## 前端 lint（eslint + type-check）
	cd frontend && npm run type-check
	cd frontend && npm run lint

test: test-backend test-frontend ## 运行全部测试

test-backend: ## 运行后端 pytest
	cd backend && uv run pytest --tb=short -q

test-frontend: ## 前端类型检查
	cd frontend && npm run type-check

build: ## 构建前端产物
	cd frontend && npm run build

# === 生产运维（systemd → supervisor 管理前后端） ===

status: ## 查看服务状态
	sudo supervisorctl status unisub:*

restart: ## 重启后端 + 前端
	sudo supervisorctl restart unisub:unisub_backend unisub:unisub_frontend

restart-backend: ## 重启后端
	sudo supervisorctl restart unisub:unisub_backend

restart-frontend: ## 重启前端 nginx（纯静态改动只需 make build，无需重启）
	sudo supervisorctl restart unisub:unisub_frontend

logs: ## 实时跟踪后端日志
	tail -f backend/logs/unisub.log

clean: ## 清理构建产物和缓存
	rm -rf frontend/dist
	rm -rf backend/.pytest_cache
	rm -rf backend/.ruff_cache
	find backend -type d -name __pycache__ -not -path "*/.venv/*" -exec rm -rf {} + 2>/dev/null || true
