"""Emby 图片代理路由 — 独立于 JWT 鉴权，用 HMAC 签名校验。

浏览器 <img> 请求无法携带 Authorization 头，因此本路由不挂在
get_current_user 依赖下，改用短期 HMAC 签名 URL（见 core/image_sign.py）。
历史上图片直链把 Emby api_key 拼进查询串，泄露给浏览器与访问日志，
现由后端代理取图，密钥只出现在服务端到 Emby 的请求里。
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.core.http_client import HttpRequestError
from app.core.image_sign import verify_emby_image_sig
from app.core.logger import init_logger
from app.services import require_emby_service
from app.services.emby.service import EmbyService

router = APIRouter(prefix="/api/emby", tags=["Emby 媒体库"])
logger = init_logger()


@router.get("/image/{emby_id}")
async def emby_image_proxy(
    emby_id: str,
    exp: int,
    sig: str,
    emby: EmbyService = Depends(require_emby_service),
) -> Response:
    """代理 Emby Primary 海报 — 校验签名后转发，避免 api_key 暴露给浏览器。

    Args:
        emby_id: Emby 条目 ID
        exp: 签名过期 Unix 时间戳
        sig: HMAC 签名

    Returns:
        图片字节流（带浏览器缓存头）
    """
    if not verify_emby_image_sig(emby_id, exp, sig):
        raise HTTPException(status_code=403, detail="图片链接无效或已过期")
    try:
        data, content_type = await emby.get_primary_image(emby_id)
    except HttpRequestError as e:
        raise HTTPException(status_code=502, detail=f"Emby 图片获取失败: {e}") from e
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "public, max-age=3600"})
