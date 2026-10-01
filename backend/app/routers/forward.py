"""Forward API 路由 — 极简订阅管理接口，对齐 forward app 期望。

所有路由路径保持与 mp2ne 一致（/api/v1/...），供 forward app 消费。
登录端点返回 JWT token，其余端点通过 Bearer 鉴权保护。
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import login_guard
from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.logger import init_logger
from app.schemas.forward import (
    ForwardActionResponse,
    ForwardSearchItem,
    ForwardSubscribeInput,
)
from app.services import get_mp_service, get_nf_service, get_tmdb_service
from app.services.auth_config import load_auth_config
from app.services.forward import ForwardService
from app.services.orchestrator import OrchestratorService

router = APIRouter(tags=["Forward API"])
logger = init_logger()


async def _get_forward_service(db: AsyncSession) -> ForwardService:
    """创建 ForwardService 实例。

    Args:
        db: 数据库会话

    Returns:
        ForwardService 实例

    Raises:
        HTTPException: NextFind 未配置
    """
    nf = await get_nf_service(db)
    if not nf:
        raise HTTPException(status_code=503, detail="NextFind 平台未配置或未启用")
    mp = await get_mp_service(db)
    tmdb = await get_tmdb_service(db)
    orchestrator = OrchestratorService(nf, mp, tmdb)
    return ForwardService(nf, orchestrator)


def _login_lock_key(request: Request, username: str) -> str:
    """构造登录限流键 —— 来源 IP + 用户名。

    按组合计数：本系统只有一个有效账号，组合键足以卡死针对该账号的爆破，
    同时避免共享出口 IP 的攻击者把其他来源的用户一起锁死。

    Args:
        request: 当前请求（取 client host）
        username: 表单里的用户名

    Returns:
        限流键字符串
    """
    client = request.client
    ip = client.host if client else "unknown"
    return f"{ip}|{username.strip().lower()}"


@router.post("/api/v1/login/access-token", response_model=dict)
async def forward_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """登录 — 验证凭据，返回 JWT token。

    使用 Form 参数接收用户名密码，与 MoviePilot 风格兼容。
    失败计数达上限后按指数退避锁定该来源（5 次失败锁 5 分钟，逐级翻倍），
    锁定期间返回 429 且不校验凭据。
    """
    lock_key = _login_lock_key(request, username)
    locked, remaining = login_guard.is_locked(lock_key)
    if locked:
        logger.warning(f"Forward 登录被锁定拒绝: key={lock_key!r}, 剩余 {remaining}s")
        raise HTTPException(
            status_code=429,
            detail=f"登录失败次数过多，请 {remaining} 秒后重试",
            headers={"Retry-After": str(remaining)},
        )

    svc = await _get_forward_service(db)
    auth = load_auth_config()
    result = await svc.login(
        username=username,
        password=password,
        config_username=auth.get("username", ""),
        config_password=auth.get("password", ""),
    )

    if "success" in result and not result["success"]:
        login_guard.record_failure(lock_key)
        raise HTTPException(status_code=401, detail=result.get("message", "登录失败"))

    login_guard.reset(lock_key)
    logger.info(f"Forward 登录成功: {username}")
    return result


@router.get("/api/v1/auth/info", response_model=dict)
async def forward_auth_info(
    db: AsyncSession = Depends(get_db),
    _current_user: str = Depends(get_current_user),
):
    """获取当前 Forward 账号信息。"""
    svc = await _get_forward_service(db)
    auth = load_auth_config()
    return await svc.get_auth_info(auth.get("username", ""), auth.get("password", ""))


@router.put("/api/v1/auth/update", response_model=ForwardActionResponse)
async def forward_auth_update(
    body: dict,
    db: AsyncSession = Depends(get_db),
    _current_user: str = Depends(get_current_user),
):
    """更新 Forward 账号密码。

    修改后需要重新登录。
    """
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    if not username or not password:
        return ForwardActionResponse(success=False, message="用户名和密码不能为空", data={})

    svc = await _get_forward_service(db)
    ok = await svc.update_auth(username, password)
    if ok:
        return ForwardActionResponse(success=True, message="账号密码已更新", data={})
    return ForwardActionResponse(success=False, message="保存失败", data={})


@router.get("/api/v1/media/search", response_model=list[ForwardSearchItem])
async def forward_search(
    title: str = Query(..., description="搜索关键词"),
    type: str = Query("media", description="媒体类型"),
    page: int = Query(1, description="页码"),
    count: int = Query(8, description="每页数量"),
    db: AsyncSession = Depends(get_db),
    _current_user: str = Depends(get_current_user),
):
    """搜索媒体 — 调用 NextFind OpenAPI 搜索。

    需要 JWT 鉴权。
    """
    svc = await _get_forward_service(db)
    results = await svc.search(title, type)
    return results[:count]


@router.get("/api/v1/subscribe/", response_model=list[dict])
async def forward_list_subscribes(
    db: AsyncSession = Depends(get_db),
    _current_user: str = Depends(get_current_user),
):
    """获取订阅列表 — 从本地数据库读取。

    需要 JWT 鉴权。
    """
    svc = await _get_forward_service(db)
    return await svc.list_subscribes(db)


@router.get("/api/v1/subscribe/user", response_model=list[dict])
@router.get("/api/v1/subscribe/user/", response_model=list[dict])
@router.get("/api/v1/subscribe/user/{username}", response_model=list[dict])
async def forward_list_user_subscribes(
    username: str | None = None,
    db: AsyncSession = Depends(get_db),
    _current_user: str = Depends(get_current_user),
):
    """获取用户订阅列表 — 兼容 forward app 调用。

    实际上忽略 username 参数，返回全部订阅列表。
    """
    svc = await _get_forward_service(db)
    return await svc.list_subscribes(db)


@router.post("/api/v1/subscribe/", response_model=ForwardActionResponse)
async def forward_add_subscribe(
    body: ForwardSubscribeInput,
    db: AsyncSession = Depends(get_db),
    _current_user: str = Depends(get_current_user),
):
    """添加订阅 — 委托 OrchestratorService 创建本地记录 + 推送到 NextFind。

    需要 JWT 鉴权。
    """
    svc = await _get_forward_service(db)
    return await svc.add_subscribe(db, body)


@router.get("/api/v1/subscribe/media/{mediaid}", response_model=dict)
async def forward_subscribe_detail(
    mediaid: str,
    season: int | None = Query(None, description="季号"),
    title: str | None = Query(None, description="媒体标题"),
    db: AsyncSession = Depends(get_db),
    _current_user: str = Depends(get_current_user),
):
    """获取订阅详情 — 从本地数据库查询单条记录。

    支持 tmdb:123 格式的 mediaid。
    需要 JWT 鉴权。
    """
    tmdb_id = None
    if mediaid.startswith("tmdb:"):
        raw = mediaid[5:]
        if raw.isdigit():
            tmdb_id = int(raw)
    elif mediaid.isdigit():
        tmdb_id = int(mediaid)

    if tmdb_id is None:
        return {"id": None, "tmdbid": None, "name": None, "type": None}

    svc = await _get_forward_service(db)
    return await svc.get_subscribe_detail(db, tmdb_id)


@router.delete("/api/v1/subscribe/media/{mediaid}", response_model=ForwardActionResponse)
async def forward_delete_subscribe(
    mediaid: str,
    season: int | None = Query(None, description="季号"),
    db: AsyncSession = Depends(get_db),
    _current_user: str = Depends(get_current_user),
):
    """删除订阅 — 委托 OrchestratorService 取消订阅。

    仅支持 tmdb: 格式的 mediaid。
    需要 JWT 鉴权。
    """
    if not mediaid.startswith("tmdb:"):
        return ForwardActionResponse(success=False, message="仅支持 tmdb: 格式媒体删除", data={})

    raw = mediaid[5:]
    if not raw.isdigit():
        return ForwardActionResponse(success=False, message="tmdbid 无效", data={})

    svc = await _get_forward_service(db)
    return await svc.remove_subscribe(db, int(raw))


@router.delete("/api/v1/subscribe/", response_model=ForwardActionResponse)
async def forward_delete_subscribe_body(
    body: ForwardSubscribeInput,
    db: AsyncSession = Depends(get_db),
    _current_user: str = Depends(get_current_user),
):
    """删除订阅 — 通过请求体指定 tmdbid。

    兼容 forward app 通过 POST body 删除的方式。
    """
    tmdb_id = body.tmdbid or 0
    if not tmdb_id and body.mediaid:
        if body.mediaid.startswith("tmdb:"):
            raw = body.mediaid[5:]
            if raw.isdigit():
                tmdb_id = int(raw)

    if tmdb_id <= 0:
        return ForwardActionResponse(success=False, message="tmdbid 无效", data={})

    svc = await _get_forward_service(db)
    return await svc.remove_subscribe(db, tmdb_id)


@router.get("/api/v1/openapi/subscribe", response_model=dict)
async def forward_openapi_subscribe(
    db: AsyncSession = Depends(get_db),
    _current_user: str = Depends(get_current_user),
):
    """OpenAPI 风格的订阅列表查询。

    需要 JWT 鉴权。
    """
    svc = await _get_forward_service(db)
    data = await svc.list_subscribes(db)
    return {"code": 0, "msg": "success", "data": data}
