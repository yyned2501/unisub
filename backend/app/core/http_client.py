"""HTTP 客户端模块 — 封装 httpx.AsyncClient，提供统一的异步请求方法。"""

import httpx

from app.core.logger import init_logger

logger = init_logger()


class AsyncHttpClient:
    """异步 HTTP 客户端单例，封装 httpx.AsyncClient。

    特性:
        - 自动跟随重定向（包括 307）
        - 30 秒超时
        - 统一 JSON 解析与错误处理
        - 支持同步上下文管理器（async with）
    """

    _instance: "AsyncHttpClient | None" = None

    def __new__(cls) -> "AsyncHttpClient":
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._client: httpx.AsyncClient | None = None
            cls._instance = instance
        return cls._instance

    async def _ensure_client(self) -> httpx.AsyncClient:
        """延迟初始化 httpx 客户端，确保在事件循环中创建。"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
            )
        return self._client

    async def get(
        self, url: str, headers: dict | None = None, params: dict | None = None
    ) -> dict:
        """发送 GET 请求，返回解析后的 JSON 字典。

        Args:
            url: 请求 URL
            headers: 自定义请求头
            params: 查询参数

        Returns:
            解析后的 JSON 字典，错误时包含 "error" 和 "detail" 键
        """
        client = await self._ensure_client()
        try:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP GET {url} 失败: {e.response.status_code}")
            return {"error": f"HTTP {e.response.status_code}", "detail": str(e)}
        except Exception as e:
            logger.error(f"GET {url} 请求异常: {e}")
            return {"error": "request_failed", "detail": str(e)}

    async def post(
        self,
        url: str,
        headers: dict | None = None,
        json: dict | None = None,
        data: dict | None = None,
    ) -> dict:
        """发送 POST 请求，返回解析后的 JSON 字典。

        Args:
            url: 请求 URL
            headers: 自定义请求头
            json: JSON 请求体
            data: 表单请求体

        Returns:
            解析后的 JSON 字典，错误时包含 "error" 和 "detail" 键
        """
        client = await self._ensure_client()
        try:
            response = await client.post(
                url, headers=headers, json=json, data=data
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP POST {url} 失败: {e.response.status_code}")
            return {"error": f"HTTP {e.response.status_code}", "detail": str(e)}
        except Exception as e:
            logger.error(f"POST {url} 请求异常: {e}")
            return {"error": "request_failed", "detail": str(e)}

    async def put(
        self, url: str, headers: dict | None = None, json: dict | None = None
    ) -> dict:
        """发送 PUT 请求，返回解析后的 JSON 字典。

        Args:
            url: 请求 URL
            headers: 自定义请求头
            json: JSON 请求体

        Returns:
            解析后的 JSON 字典，错误时包含 "error" 和 "detail" 键
        """
        client = await self._ensure_client()
        try:
            response = await client.put(url, headers=headers, json=json)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP PUT {url} 失败: {e.response.status_code}")
            return {"error": f"HTTP {e.response.status_code}", "detail": str(e)}
        except Exception as e:
            logger.error(f"PUT {url} 请求异常: {e}")
            return {"error": "request_failed", "detail": str(e)}

    async def delete(
        self, url: str, headers: dict | None = None
    ) -> dict:
        """发送 DELETE 请求，返回解析后的 JSON 字典。

        Args:
            url: 请求 URL
            headers: 自定义请求头

        Returns:
            解析后的 JSON 字典，错误时包含 "error" 和 "detail" 键
        """
        client = await self._ensure_client()
        try:
            response = await client.delete(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP DELETE {url} 失败: {e.response.status_code}")
            return {"error": f"HTTP {e.response.status_code}", "detail": str(e)}
        except Exception as e:
            logger.error(f"DELETE {url} 请求异常: {e}")
            return {"error": "request_failed", "detail": str(e)}

    async def close(self):
        """关闭 HTTP 客户端连接，释放资源。"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "AsyncHttpClient":
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# 模块级单例，供 service 层直接使用
http_client = AsyncHttpClient()
