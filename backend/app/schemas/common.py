"""Schemas 公共工具 — 跨响应模型复用的字段级脱敏。

``mask_api_key`` 为全项目唯一脱敏入口；含 ``api_key`` 字段的响应模型
直接继承 ``MaskedApiKeyMixin``，不要再各自写一份 serializer。
"""

from __future__ import annotations

from pydantic import field_serializer


def mask_api_key(value: str) -> str:
    """脱敏 API Key，只保留前 4 位和后 4 位，中间用 **** 替代。"""
    if not value or len(value) <= 8:
        return "****"
    return f"{value[:4]}****{value[-4:]}"


class MaskedApiKeyMixin:
    """为含 ``api_key`` 字段的响应模型提供统一的序列化脱敏。"""

    @field_serializer("api_key")
    def _serialize_api_key(self, value: str) -> str:
        return mask_api_key(value)
