"""Emby 图片代理 URL 签名 — 避免 api_key 泄露到浏览器。

浏览器 <img> 请求无法携带 Authorization 头，历史方案把 Emby api_key
直接拼进图片 URL 查询串，导致密钥进入浏览器记录/访问日志。
现改为 HMAC 短期签名：签名由服务端密钥 + emby_id + 过期时间计算，
泄露签名无法反推密钥，且过期自动失效。
"""

from __future__ import annotations

import hashlib
import hmac
import time

from app.config import parse_config

_IMAGE_PATH_PREFIX = "/api/emby/image/"
_DEFAULT_TTL = 86400  # 签名有效期 1 天，页面每次加载都会重新签发

# 签名密钥取模块级单例：parse_config() 未配置 JWT 密钥时每次调用都会生成新随机值，
# 不能在每个请求里重复调用，否则签发与校验用的密钥不一致
_SECRET = parse_config().jwt_secret.encode()


def sign_emby_image_path(emby_id: str, ttl: int = _DEFAULT_TTL) -> str:
    """生成带签名的 Emby 图片代理路径。

    Args:
        emby_id: Emby 条目 ID
        ttl: 签名有效期（秒）

    Returns:
        形如 ``/api/emby/image/{emby_id}?exp=...&sig=...`` 的相对路径
    """
    exp = int(time.time()) + ttl
    sig = hmac.new(_SECRET, f"{emby_id}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{_IMAGE_PATH_PREFIX}{emby_id}?exp={exp}&sig={sig}"


def verify_emby_image_sig(emby_id: str, exp: int, sig: str) -> bool:
    """校验图片代理请求的签名与有效期。

    Args:
        emby_id: 路径中的 Emby 条目 ID
        exp: 请求携带的过期 Unix 时间戳
        sig: 请求携带的 HMAC 签名

    Returns:
        签名有效且未过期返回 True
    """
    if exp < int(time.time()):
        return False
    expected = hmac.new(_SECRET, f"{emby_id}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(expected, sig)
