"""海报 URL 公共工具 — 统一处理 TMDB 和 NextFind 的海报路径解析。"""

from __future__ import annotations

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


def build_tmdb_poster_url(poster_path: str | None) -> str | None:
    """根据 TMDB poster_path 构建完整图片 URL。

    Args:
        poster_path: TMDB API 返回的 poster_path（如 /abc123.jpg）

    Returns:
        完整 URL（如 https://image.tmdb.org/t/p/w500/abc123.jpg）或 None
    """
    if not poster_path:
        return None
    return f"{TMDB_IMAGE_BASE}{poster_path}"


def resolve_nf_poster(poster_value: str | None, base_url: str) -> str | None:
    """解析 NextFind 返回的海报字段为完整 URL。

    处理三种情况：完整 URL 直接返回、相对路径拼接 base_url、其他原样返回。

    Args:
        poster_value: poster 字段原始值（可能为相对路径、完整 URL 或 None）
        base_url: NextFind 基础地址（如 http://192.168.31.10:8092）

    Returns:
        完整 URL 或 None
    """
    if not poster_value:
        return None
    if poster_value.startswith(("http://", "https://")):
        return poster_value
    if poster_value.startswith("/"):
        return f"{base_url}{poster_value}"
    return poster_value
