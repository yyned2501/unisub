"""Forward API 服务 — 极简字段包装，复用 UniSub 编排层。

封装 forward app 需要的搜索、订阅 CRUD 和登录逻辑。
所有订阅操作委托给 OrchestratorService（本地记录 + NextFind 推送）。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token
from app.core.logger import init_logger
from app.models.subscription import Subscription
from app.schemas.forward import (
    ForwardActionResponse,
    ForwardSubscribeInput,
)
from app.services.auth_config import get_effective_auth, save_auth_config
from app.services.nextfind import NextFindService
from app.services.orchestrator import OrchestratorService

logger = init_logger()

_TYPE_MAP = {
    "movie": "电影",
    "tv": "电视剧",
}


def _infer_media_type(raw: str | None) -> str:
    """推断媒体类型中文名。

    Args:
        raw: 原始类型（movie / tv / 电影 / 电视剧）

    Returns:
        "电影" 或 "电视剧"
    """
    if not raw:
        return "电影"
    raw_lower = raw.strip().lower()
    if raw_lower in ("tv", "电视剧", "剧集"):
        return "电视剧"
    return "电影"


def _build_subscribe_item(sub: Subscription) -> dict:
    """构建极简订阅项。

    Args:
        sub: 订阅 ORM 模型

    Returns:
        极简字段字典
    """
    is_tv = sub.media_type == "tv"
    item = {
        "id": sub.tmdb_id,
        "tmdbid": sub.tmdb_id,
        "name": sub.title,
        "type": "电视剧" if is_tv else "电影",
    }
    if is_tv:
        item["total_episode"] = None
        item["lack_episode"] = sub.nf_missing_eps
        item["completed_episode"] = None
    return item


class ForwardService:
    """Forward API 服务 — 极简字段包装，复用 UniSub 编排层。

    搜索委托 NextFindService，订阅 CRUD 委托 OrchestratorService。
    登录使用本地 JWT 验证。
    """

    def __init__(self, nf_service: NextFindService, orchestrator: OrchestratorService):
        """初始化 Forward 服务。

        Args:
            nf_service: NextFind 服务实例
            orchestrator: 编排服务实例
        """
        self.nf = nf_service
        self.orchestrator = orchestrator

    async def login(self, username: str, password: str, config_username: str, config_password: str) -> dict:
        """本地登录验证，返回 JWT token。

        优先使用文件持久化的账号密码，fallback 到环境变量。

        Args:
            username: 用户名
            password: 密码
            config_username: 配置中的用户名
            config_password: 配置中的密码

        Returns:
            MP 风格登录响应字典
        """
        effective_username, effective_password = get_effective_auth(config_username, config_password)

        if username != effective_username or password != effective_password:
            logger.warning(f"Forward 登录失败: 用户名或密码错误 (username={username!r})")
            return {"success": False, "message": "用户名或密码错误", "data": None}

        token = create_access_token(username)
        logger.info(f"Forward 登录成功: {username}")
        return {
            "access_token": token,
            "token_type": "bearer",
            "super_user": True,
            "user_id": 1,
            "user_name": username,
            "avatar": "",
        }

    async def get_auth_info(self, config_username: str, config_password: str) -> dict:
        """获取当前生效的账号信息（不返回密码明文）。

        Args:
            config_username: 配置中的用户名
            config_password: 配置中的密码

        Returns:
            账号信息
        """
        username, _ = get_effective_auth(config_username, config_password)
        return {"username": username}

    async def update_auth(self, username: str, password: str) -> bool:
        """更新 Forward 账号密码（持久化到文件）。

        Args:
            username: 新用户名
            password: 新密码

        Returns:
            是否成功
        """
        try:
            save_auth_config(username, password)
            logger.info(f"Forward 账号密码已更新: username={username!r}")
            return True
        except Exception as e:
            logger.error(f"Forward 账号密码更新失败: {e}")
            return False

    async def search(self, query: str, media_type: str = "all") -> list[dict]:
        """搜索媒体 — 委托 NextFindService，映射为极简字段。

        Args:
            query: 搜索关键词
            media_type: 媒体类型（movie / tv / all）

        Returns:
            搜索结果列表
        """
        raw_results = await self.nf.search_tmdb(query, media_type)

        items: list[dict] = []
        for item in raw_results:
            items.append(
                {
                    "title": item.get("title") or item.get("name"),
                    "en_title": item.get("en_title") or item.get("original_title"),
                    "year": item.get("year")
                    or (item.get("release_date", "")[:4] if item.get("release_date") else None),
                    "type": item.get("type") or item.get("media_type") or media_type,
                    "season": item.get("season"),
                    "tmdb_id": item.get("tmdb_id") or item.get("id"),
                    "imdb_id": item.get("imdb_id"),
                    "douban_id": item.get("douban_id"),
                    "overview": item.get("overview"),
                    "vote_average": item.get("vote_average", 0.0),
                    "poster_path": item.get("poster_path") or item.get("poster", ""),
                    "detail_link": item.get("detail_link"),
                }
            )

        logger.info(f"Forward 搜索完成: q='{query}', type={media_type}, 结果 {len(items)} 条")
        return items

    async def list_subscribes(self, db: AsyncSession) -> list[dict]:
        """获取活跃订阅列表 — 从本地 DB 读取，仅返回 NextFind 上活跃的订阅。

        Args:
            db: 数据库会话

        Returns:
            订阅列表（极简字段）
        """
        result = await db.execute(
            select(Subscription).where(Subscription.nf_status == "active").order_by(Subscription.created_at.desc())
        )
        subs = result.scalars().all()

        return [_build_subscribe_item(sub) for sub in subs]

    async def get_subscribe_detail(self, db: AsyncSession, tmdb_id: int) -> dict:
        """获取单条订阅详情 — 从本地 DB 查。

        Args:
            db: 数据库会话
            tmdb_id: TMDB ID

        Returns:
            订阅详情（极简字段），未找到时返回空值
        """
        result = await db.execute(select(Subscription).where(Subscription.tmdb_id == tmdb_id))
        sub = result.scalar_one_or_none()
        if not sub:
            return {"id": None, "tmdbid": None, "name": None, "type": None}
        return _build_subscribe_item(sub)

    async def add_subscribe(self, db: AsyncSession, body: ForwardSubscribeInput) -> ForwardActionResponse:
        """添加订阅 — 委托 OrchestratorService。

        Args:
            db: 数据库会话
            body: 订阅请求体

        Returns:
            操作结果
        """
        tmdbid = body.tmdbid or 0
        media_type = body.type or "movie"

        # 从 mediaid 解析 tmdbid
        if not tmdbid and body.mediaid:
            if body.mediaid.startswith("tmdb:"):
                raw = body.mediaid[5:]
                if raw.isdigit():
                    tmdbid = int(raw)

        if tmdbid <= 0:
            return ForwardActionResponse(success=False, message="tmdbid 无效", data={})

        media_type = "tv" if _infer_media_type(media_type) == "电视剧" else "movie"
        title = body.name or f"tmdb_{tmdbid}"

        try:
            await self.orchestrator.subscribe(
                db=db,
                tmdb_id=tmdbid,
                title=title,
                media_type=media_type,
                source="forward",
            )
            return ForwardActionResponse(
                success=True,
                message="订阅成功",
                data={"id": tmdbid},
            )
        except Exception as e:
            logger.error(f"Forward 添加订阅失败: tmdb_id={tmdbid}, error={e}")
            return ForwardActionResponse(success=False, message=f"订阅失败: {e}", data={})

    async def remove_subscribe(self, db: AsyncSession, tmdb_id: int) -> ForwardActionResponse:
        """删除订阅 — 委托 OrchestratorService。

        Args:
            db: 数据库会话
            tmdb_id: TMDB ID

        Returns:
            操作结果
        """
        # 查找本地订阅记录
        result = await db.execute(select(Subscription).where(Subscription.tmdb_id == tmdb_id))
        sub = result.scalar_one_or_none()
        if not sub:
            return ForwardActionResponse(success=False, message="订阅记录不存在", data={})

        try:
            unsub_result = await self.orchestrator.unsubscribe(db, sub.id)
            if unsub_result.get("success"):
                return ForwardActionResponse(success=True, message="取消订阅成功", data={})
            return ForwardActionResponse(success=False, message=unsub_result.get("message", "取消订阅失败"), data={})
        except Exception as e:
            logger.error(f"Forward 删除订阅失败: tmdb_id={tmdb_id}, error={e}")
            return ForwardActionResponse(success=False, message=f"取消订阅失败: {e}", data={})
