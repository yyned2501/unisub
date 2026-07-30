"""自动订阅流水线包 — 拆分自原 pipeline.py。"""

from app.services.auto_subscribe.pipeline.runner import run

__all__ = ["run"]
