"""路由层 — 统一导出所有 API 路由。"""

from app.routers.auto_subscribe import router as auto_subscribe_router
from app.routers.cd2 import router as cd2_router
from app.routers.dashboard import router as dashboard_router
from app.routers.emby import router as emby_router
from app.routers.forward import router as forward_router
from app.routers.logs import router as logs_router
from app.routers.platforms import router as platforms_router
from app.routers.search import router as search_router
from app.routers.subscriptions import router as subscriptions_router
from app.routers.tasks import router as tasks_router

__all__ = [
    "auto_subscribe_router",
    "cd2_router",
    "dashboard_router",
    "emby_router",
    "forward_router",
    "logs_router",
    "platforms_router",
    "search_router",
    "subscriptions_router",
    "tasks_router",
]