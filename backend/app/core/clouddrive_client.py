"""CloudDrive2 gRPC 客户端封装。"""

import grpc
from google.protobuf import descriptor_pb2, empty_pb2, timestamp_pb2

from app.core import clouddrive_pb2, clouddrive_pb2_grpc


class CloudDriveClient:
    """CloudDrive2 异步 gRPC 客户端。"""

    def __init__(self, address: str, api_key: str) -> None:
        """初始化客户端。"""
        self._address = self._normalize_address(address)
        self._metadata = (("authorization", f"Bearer {api_key}"),)

    async def test_connection(self) -> dict[str, str | bool]:
        """验证服务地址和 API Token 是否可用于文件操作。"""
        async with grpc.aio.insecure_channel(self._address) as channel:
            stub = clouddrive_pb2_grpc.CloudDriveFileSrvStub(channel)
            system_info = await stub.GetSystemInfo(empty_pb2.Empty(), timeout=10)
            stream = stub.GetSubFiles(
                clouddrive_pb2.ListSubFileRequest(path="/", forceRefresh=False),
                metadata=self._metadata,
                timeout=10,
            )
            async for _ in stream:
                break

        return {
            "connected": True,
            "system_ready": system_info.SystemReady,
            "is_login": system_info.IsLogin,
            "user_name": system_info.UserName,
        }

    async def find_file_by_path(self, path: str) -> dict | None:
        """通过路径在 CD2 中查找文件/文件夹。

        Args:
            path: CD2 中的完整路径

        Returns:
            CloudDriveFile 信息字典，未找到时返回 None
        """
        if not path or path == "/":
            return None
        parent_path = "/".join(path.rstrip("/").split("/")[:-1]) or "/"
        file_name = path.rstrip("/").split("/")[-1]
        async with grpc.aio.insecure_channel(self._address) as channel:
            stub = clouddrive_pb2_grpc.CloudDriveFileSrvStub(channel)
            request = clouddrive_pb2.FindFileByPathRequest(
                parentPath=parent_path,
                path=file_name,
            )
            try:
                result = await stub.FindFileByPath(request, metadata=self._metadata, timeout=10)
                if result and result.name:
                    return {
                        "name": result.name,
                        "path": result.fullPathName or path,
                        "file_type": result.fileType,
                        "exists": True,
                    }
            except Exception:
                pass
        return None

    async def list_sub_files(self, path: str) -> list[dict]:
        """列出目录中的文件和子目录。

        Args:
            path: 目录路径

        Returns:
            CloudDriveFile 信息列表
        """
        async with grpc.aio.insecure_channel(self._address) as channel:
            stub = clouddrive_pb2_grpc.CloudDriveFileSrvStub(channel)
            request = clouddrive_pb2.ListSubFileRequest(path=path, forceRefresh=False)
            files = []
            try:
                stream = stub.GetSubFiles(request, metadata=self._metadata, timeout=15)
                async for response in stream:
                    for f in response.subFiles:
                        files.append(
                            {
                                "name": f.name,
                                "path": f.fullPathName,
                                "file_type": f.fileType,
                                "size": f.size,
                                "is_dir": f.isDirectory,
                            }
                        )
            except Exception:
                pass
        return files

    async def get_download_url(self, path: str) -> str | None:
        """获取文件的下载 URL。

        Args:
            path: 文件路径

        Returns:
            下载 URL 或 None
        """
        async with grpc.aio.insecure_channel(self._address) as channel:
            stub = clouddrive_pb2_grpc.CloudDriveFileSrvStub(channel)
            request = clouddrive_pb2.GetDownloadUrlPathRequest(
                path=path,
                preview=False,
                lazy_read=False,
                get_direct_url=True,
            )
            try:
                result = await stub.GetDownloadUrlPath(request, metadata=self._metadata, timeout=15)
                if result.downloadUrlPath:
                    scheme = "http"
                    host = self._address
                    return (
                        result.downloadUrlPath.replace("{SCHEME}", scheme)
                        .replace("{HOST}", host)
                        .replace("{PREVIEW}", "false")
                    )
                if result.directUrl:
                    return result.directUrl
            except Exception:
                pass
        return None

    async def rename_file(self, file_path: str, new_name: str) -> bool:
        """重命名文件或文件夹。

        Args:
            file_path: 当前文件路径
            new_name: 新文件名（不含路径）

        Returns:
            是否成功
        """
        async with grpc.aio.insecure_channel(self._address) as channel:
            stub = clouddrive_pb2_grpc.CloudDriveFileSrvStub(channel)
            request = clouddrive_pb2.RenameFileRequest(
                theFilePath=file_path,
                newName=new_name,
            )
            try:
                result = await stub.RenameFile(request, metadata=self._metadata, timeout=15)
                return result.success
            except Exception:
                return False

    async def ensure_directory(self, path: str) -> bool:
        """确保目标目录存在，不存在则创建。

        Args:
            path: CD2 目录路径

        Returns:
            是否成功
        """
        async with grpc.aio.insecure_channel(self._address) as channel:
            stub = clouddrive_pb2_grpc.CloudDriveFileSrvStub(channel)
            if path in ("/", ""):
                return True
            parent_path = "/".join(path.rstrip("/").split("/")[:-1]) or "/"
            folder_name = path.rstrip("/").split("/")[-1]
            request = clouddrive_pb2.CreateFolderRequest(
                parentPath=parent_path,
                folderName=folder_name,
            )
            try:
                result = await stub.CreateFolder(request, metadata=self._metadata, timeout=10)
                return result.result.success
            except Exception:
                return False

    async def move_file(self, source_paths: list[str], dest_path: str) -> bool:
        """将文件/文件夹移动到目标目录。

        Args:
            source_paths: 源文件路径列表
            dest_path: 目标目录路径

        Returns:
            是否成功
        """
        async with grpc.aio.insecure_channel(self._address) as channel:
            stub = clouddrive_pb2_grpc.CloudDriveFileSrvStub(channel)
            request = clouddrive_pb2.MoveFileRequest(
                theFilePaths=source_paths,
                destPath=dest_path,
                conflictPolicy=clouddrive_pb2.MoveFileRequest.Rename,
            )
            try:
                result = await stub.MoveFile(request, metadata=self._metadata, timeout=30)
                return result.success
            except Exception:
                return False

    @staticmethod
    def _normalize_address(address: str) -> str:
        """将用户输入的 URL 转换为 gRPC 地址。"""
        normalized = address.strip().rstrip("/")
        for prefix in ("http://", "https://"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :]
                break
        if not normalized:
            raise ValueError("CloudDrive2 URL 不能为空")
        return normalized
