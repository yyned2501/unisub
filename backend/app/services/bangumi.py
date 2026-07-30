"""Bangumi API v0 客户端 — 获取番剧别名以辅助 TMDB 搜索。"""

from __future__ import annotations

from typing import Any

from app.core.http_client import http_client
from app.core.logger import init_logger

logger = init_logger(__name__)

_BASE_URL = "https://api.bgm.tv"

# 别名在 infobox 中的 key 名
_ALIAS_KEY = "别名"


class BangumiService:
    """Bangumi API v0 客户端，用于通过 Bangumi ID 获取番剧候选标题。"""

    async def get_subject(self, bangumi_id: int) -> dict[str, Any] | None:
        """获取番剧详情。

        Args:
            bangumi_id: Bangumi 条目 ID

        Returns:
            详情字典，或 None（获取失败/条目不存在）
        """
        url = f"{_BASE_URL}/v0/subjects/{bangumi_id}"
        headers = {"User-Agent": "UniSub/1.0"}
        result = await http_client.get(url, headers=headers)
        if "error" in result:
            logger.warning("[Bangumi] 获取失败: id=%d, error=%s", bangumi_id, result.get("error"))
            return None
        return result

    @staticmethod
    def get_candidate_titles(subject: dict[str, Any]) -> list[str]:
        """从 Bangumi 详情中提取候选标题列表（用于 TMDB 搜索）。

        优先级：name_cn（中文标题）→ name（日文标题）→ 别名中的中/英/日文标题。
        去重后返回，保留原始顺序。

        Args:
            subject: get_subject 返回的详情字典

        Returns:
            候选标题列表（按优先级排序）
        """
        candidates: list[str] = []

        name_cn = subject.get("name_cn", "").strip()
        name = subject.get("name", "").strip()

        if name_cn:
            candidates.append(name_cn)
        if name and name != name_cn:
            candidates.append(name)

        # 从 infobox 提取别名
        for entry in subject.get("infobox") or []:
            if not isinstance(entry, dict):
                continue
            if entry.get("key") != _ALIAS_KEY:
                continue
            value = entry.get("value")
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        v = str(item.get("v", "")).strip()
                        if v and v not in candidates:
                            candidates.append(v)
            elif isinstance(value, str):
                v = value.strip()
                if v and v not in candidates:
                    candidates.append(v)

        return candidates

    @staticmethod
    def get_type(subject: dict[str, Any]) -> int | None:
        """获取番剧类型（2=动画, 1=书籍/漫画, 3=音乐, 4=游戏, 6=三次元）。

        Args:
            subject: get_subject 返回的详情字典

        Returns:
            类型数字，或 None
        """
        return subject.get("type")

    @staticmethod
    def get_year(subject: dict[str, Any]) -> str | None:
        """从 Bangumi 详情中提取年份。

        Args:
            subject: get_subject 返回的详情字典

        Returns:
            年份字符串（如 "2024"），或 None
        """
        date_str = subject.get("date") or ""
        parts = date_str.split("-")
        return parts[0] if parts[0].isdigit() else None

    @staticmethod
    def is_anime(subject: dict[str, Any]) -> bool:
        """判断是否为动画（type=2）。

        Args:
            subject: get_subject 返回的详情字典

        Returns:
            是动画返回 True
        """
        return subject.get("type") == 2
