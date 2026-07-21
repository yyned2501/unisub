"""CloudDrive2 外部 API 服务。"""

from app.core.clouddrive_client import CloudDriveClient


class CloudDrive2Service:
    """CloudDrive2 gRPC API 服务。"""

    def __init__(self, base_url: str, api_key: str) -> None:
        """初始化 CloudDrive2 服务。"""
        self._client = CloudDriveClient(base_url, api_key)

    async def test_connection(self) -> dict[str, str | bool]:
        """测试 CloudDrive2 服务及 API Token。"""
        return await self._client.test_connection()
