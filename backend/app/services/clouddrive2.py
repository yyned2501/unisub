"""CloudDrive2 外部 API 服务。"""

from __future__ import annotations

import re

from app.core.clouddrive_client import CloudDriveClient
from app.core.logger import init_logger

logger = init_logger(__name__)


class CloudDrive2Service:
    """CloudDrive2 gRPC API 服务。"""

    def __init__(self, base_url: str, api_key: str) -> None:
        """初始化 CloudDrive2 服务。"""
        self._client = CloudDriveClient(base_url, api_key)

    async def test_connection(self) -> dict[str, str | bool]:
        """测试 CloudDrive2 服务及 API Token。"""
        return await self._client.test_connection()

    async def resolve_path(self, cd2_path: str) -> dict:
        """验证并确认 CD2 中的真实路径。

        先尝试精确匹配，再尝试父目录模糊匹配。

        Args:
            cd2_path: 预期的 CD2 路径

        Returns:
            包含 verified、cd2_path、name 等字段的字典
        """
        # 1. 精确查找
        found = await self._client.find_file_by_path(cd2_path)
        if found:
            sub_files = await self._client.list_sub_files(cd2_path)
            return {
                "verified": True,
                "cd2_path": found["path"],
                "name": found["name"],
                "file_type": "directory" if found.get("file_type") == 0 else "file",
                "sub_items": len(sub_files),
                "sub_file_names": [f["name"] for f in sub_files[:20]],
                "note": "CD2 中已确认该路径",
            }

        # 2. 逐级模糊查找
        parent_path = "/".join(cd2_path.rstrip("/").split("/")[:-1]) or "/"
        folder_name = cd2_path.rstrip("/").split("/")[-1]
        parent_files = await self._client.list_sub_files(parent_path)
        candidates = [f for f in parent_files if folder_name in f["name"]]
        if candidates:
            return {
                "verified": True,
                "cd2_path": candidates[0]["path"],
                "name": candidates[0]["name"],
                "file_type": "directory" if candidates[0].get("is_dir") else "file",
                "sub_items": len(candidates),
                "sub_file_names": [f["name"] for f in candidates],
                "note": "模糊匹配找到的路径，请确认是否正确",
            }

        return {
            "verified": False,
            "cd2_path": cd2_path,
            "note": "CD2 中未找到该路径，请手动检查",
        }

    async def move_to_pending(self, cd2_src_path: str, target_path: str) -> str:
        """重命名（去除 tmdb 标记）并移动文件夹到待整理目录。

        Args:
            cd2_src_path: 源路径
            target_path: 目标待整理目录

        Returns:
            实际使用的源路径（重命名后可能变化）

        Raises:
            RuntimeError: CD2 移动文件失败
        """
        # 1. 重命名去掉 {tmdb-xxx} 标记
        parent_path = "/".join(cd2_src_path.rstrip("/").split("/")[:-1]) or "/"
        folder_name = cd2_src_path.rstrip("/").split("/")[-1]
        new_name = re.sub(r"\s*\{tmdb-\d+\}\s*", "", folder_name).strip()

        actual_src = cd2_src_path
        if new_name and new_name != folder_name:
            rename_ok = await self._client.rename_file(cd2_src_path, new_name)
            if rename_ok:
                actual_src = f"{parent_path}/{new_name}" if parent_path != "/" else f"/{new_name}"
                logger.info("已重命名: %s → %s", folder_name, new_name)
            else:
                logger.warning("重命名失败，继续使用原路径: %s", folder_name)

        # 2. 确保目标目录存在
        await self._client.ensure_directory(target_path)

        # 3. 移动文件
        success = await self._client.move_file([actual_src], target_path)
        if not success:
            raise RuntimeError("CD2 移动文件失败，请检查路径和权限")

        return actual_src
