"""HTTP 客户端模块 — 封装 httpx.AsyncClient，提供统一的异步请求方法。

错误处理约定（全后端统一，务必遵守）:
    - get / post / put / delete: 失败时**不抛异常**，而是返回
      ``{"error": <错误码>, "detail": <详情>}`` 字典。调用方**必须**检查
      ``"error" in result`` 后再使用返回值，否则会把错误字典当成正常数据。
      推荐复用 services/nextfind.py 的 ``_check`` 辅助模式消除重复判断。
    - get_text: 用于抓取 HTML/RSS 文本，失败时**抛出** ``HttpRequestError``，
      调用方需 try/except。这是文本端点的例外约定。

    未来若引入 pytest 测试覆盖，可考虑将 get/post/... 迁移为抛异常契约，
    使错误无法被静默忽略；当前无测试，维持 error-dict 约定以保证稳定。
"""

from typing import Any

import httpx

from app.core.logger import init_logger

logger = init_logger()


class HttpRequestError(RuntimeError):
    """HTTP 请求未能成功完成时抛出的异常。"""


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

    async def get(self, url: str, headers: dict | None = None, params: dict | None = None) -> dict:
        """发送 GET 请求，返回解析后的 JSON 字典。

        Args:
            url: 请求 URL
            headers: 自定义请求头
            params: 查询参数

        Returns:
            解析后的 JSON 字典；失败时返回 ``{"error": ..., "detail": ...}``
            （不抛异常，调用方须检查 ``"error" in result``）
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

    async def get_text(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        proxy_url: str | None = None,
    ) -> str:
        """发送 GET 请求并返回原始文本，失败时抛出 HTTP 请求异常。

        Args:
            url: 请求 URL
            headers: 自定义请求头
            params: 查询参数
            proxy_url: 可选代理地址，如 "http://192.168.31.10:7890"

        Returns:
            响应正文文本

        Raises:
            HttpRequestError: 网络请求失败或服务端返回非成功状态码
        """
        if proxy_url:
            client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
                proxy=proxy_url,
            )
        else:
            client = await self._ensure_client()
        try:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            logger.error(f"HTTP GET {url} 失败: {status_code}")
            raise HttpRequestError(f"GET 请求返回 HTTP {status_code}: {url}") from e
        except httpx.RequestError as e:
            logger.error(f"GET {url} 网络请求异常: {e}")
            raise HttpRequestError(f"GET 网络请求失败: {url}") from e
        finally:
            if proxy_url:
                await client.aclose()

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
            解析后的 JSON 字典；失败时返回 ``{"error": ..., "detail": ...}``
            （不抛异常，调用方须检查 ``"error" in result``）
        """
        client = await self._ensure_client()
        try:
            response = await client.post(url, headers=headers, json=json, data=data)
            response.raise_for_status()
            # 部分接口（如 Emby 更新元数据）成功返回 204 No Content（空响应体）
            if not response.content:
                return {}
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP POST {url} 失败: {e.response.status_code}")
            return {"error": f"HTTP {e.response.status_code}", "detail": str(e)}
        except Exception as e:
            logger.error(f"POST {url} 请求异常: {e}")
            return {"error": "request_failed", "detail": str(e)}

    async def put(self, url: str, headers: dict | None = None, json: dict | None = None) -> dict:
        """发送 PUT 请求，返回解析后的 JSON 字典。

        Args:
            url: 请求 URL
            headers: 自定义请求头
            json: JSON 请求体

        Returns:
            解析后的 JSON 字典；失败时返回 ``{"error": ..., "detail": ...}``
            （不抛异常，调用方须检查 ``"error" in result``）
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

    async def delete(self, url: str, headers: dict | None = None) -> dict:
        """发送 DELETE 请求，返回解析后的 JSON 字典。

        Args:
            url: 请求 URL
            headers: 自定义请求头

        Returns:
            解析后的 JSON 字典；失败时返回 ``{"error": ..., "detail": ...}``
            （不抛异常，调用方须检查 ``"error" in result``）
        """
        client = await self._ensure_client()
        try:
            response = await client.delete(url, headers=headers)
            response.raise_for_status()
            # 部分接口删除成功返回 204 No Content（空响应体），此时返回空字典
            if not response.content:
                return {}
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP DELETE {url} 失败: {e.response.status_code}")
            return {"error": f"HTTP {e.response.status_code}", "detail": str(e)}
        except Exception as e:
            logger.error(f"DELETE {url} 请求异常: {e}")
            return {"error": "request_failed", "detail": str(e)}

    async def close(self) -> None:
        """关闭 HTTP 客户端连接，释放资源。"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "AsyncHttpClient":
        await self._ensure_client()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()


# 模块级单例，供 service 层直接使用
http_client = AsyncHttpClient()
