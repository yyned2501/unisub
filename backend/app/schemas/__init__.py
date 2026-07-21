"""Pydantic schemas — 统一导出所有请求/响应模型。"""

from app.schemas.auto_subscribe import (
    AutoSubConfigResponse,
    AutoSubConfigUpdate,
    AutoSubHistoryItem,
    AutoSubHistoryResponse,
    AutoSubMetaResponse,
    AutoSubRunResponse,
)
from app.schemas.cd2 import Cd2ConfigResponse, Cd2ConfigUpdate, Cd2TestResult
from app.schemas.dashboard import ActivityLogResponse, DashboardStats, NextFindQuota, PlatformStatus
from app.schemas.emby import (
    BlacklistActionResponse,
    BlacklistCreate,
    EmbyBlacklistEntry,
    EmbyLibraryAnalysis,
    EmbySeriesStatus,
)
from app.schemas.emby_cache import EmbyCacheResponse, EmbyMissingAnalysis, EmbySyncResult, Tmdb404Item
from app.schemas.forward import (
    ForwardActionResponse,
    ForwardLoginResponse,
    ForwardSearchItem,
    ForwardSubscribeInput,
    ForwardSubscribeItem,
    ForwardTVSubscribeItem,
)
from app.schemas.platform import PlatformConfigCreate, PlatformConfigResponse, PlatformConfigUpdate, PlatformTestResult
from app.schemas.search import SearchQuery, SearchResponse, SearchResultItem
from app.schemas.subscription import SubscriptionCreate, SubscriptionResponse, SubscriptionSyncResult

__all__ = [
    "ActivityLogResponse",
    "AutoSubConfigResponse",
    "AutoSubConfigUpdate",
    "AutoSubHistoryItem",
    "AutoSubHistoryResponse",
    "AutoSubMetaResponse",
    "AutoSubRunResponse",
    "BlacklistActionResponse",
    "BlacklistCreate",
    "Cd2ConfigResponse",
    "Cd2ConfigUpdate",
    "Cd2TestResult",
    "DashboardStats",
    "EmbyBlacklistEntry",
    "EmbyCacheResponse",
    "EmbyLibraryAnalysis",
    "EmbyMissingAnalysis",
    "EmbySeriesStatus",
    "EmbySyncResult",
    "Tmdb404Item",
    "ForwardActionResponse",
    "ForwardLoginResponse",
    "ForwardSearchItem",
    "ForwardSubscribeInput",
    "ForwardSubscribeItem",
    "ForwardTVSubscribeItem",
    "NextFindQuota",
    "PlatformConfigCreate",
    "PlatformConfigResponse",
    "PlatformConfigUpdate",
    "PlatformStatus",
    "PlatformTestResult",
    "SearchQuery",
    "SearchResponse",
    "SearchResultItem",
    "SubscriptionCreate",
    "SubscriptionResponse",
    "SubscriptionSyncResult",
]
