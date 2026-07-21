"""自动订阅服务的公开接口。"""

from app.services.auto_subscribe.models import DEFAULT_CONFIG, SOURCE_NAMES, STATUS_LABELS
from app.services.auto_subscribe.pipeline import run
from app.services.auto_subscribe.service import get_auto_subscribe_service

__all__ = [
    "run",
    "get_auto_subscribe_service",
    "DEFAULT_CONFIG",
    "SOURCE_NAMES",
    "STATUS_LABELS",
]
