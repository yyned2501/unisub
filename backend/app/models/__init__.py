"""数据模型 — 所有 ORM 模型在此导出以确保 Base.metadata 注册。"""

from app.models.activity_log import ActivityLog
from app.models.cd2_config import Cd2Config
from app.models.emby_blacklist import EmbyBlacklist
from app.models.emby_cache import EmbyCache
from app.models.platform_config import PlatformConfig
from app.models.subscription import Subscription
from app.models.tmdb_cache import TmdbCache

__all__ = [
    "ActivityLog",
    "Cd2Config",
    "EmbyBlacklist",
    "EmbyCache",
    "PlatformConfig",
    "Subscription",
    "TmdbCache",
]
