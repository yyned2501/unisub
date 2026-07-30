"""路由层 — 所有 API 路由模块。

main.py 通过 `from app.routers import <module>` 导入各模块，
再调用 `app.include_router(<module>.router)` 注册。
"""

__all__ = [
    "ai",
    "auto_subscribe",
    "cd2",
    "dashboard",
    "emby",
    "forward",
    "logs",
    "platforms",
    "search",
    "subscriptions",
    "tasks",
]
