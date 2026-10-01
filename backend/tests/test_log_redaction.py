"""日志脱敏测试 — URL query string（含 api_key 等密钥）不得进入日志或错误详情。

这是「日志洩密」的回归测试：TMDB 的 ``?api_key=xxx`` 曾经随 httpx 异常消息
整条落到 backend/logs 下，改回裸 URL 就会在这里炸掉。
"""

import logging

import httpx
import pytest

from app.core.http_client import AsyncHttpClient, HttpRequestError, strip_query

SECRET = "REALSECRET0123456789"
SECRET_URL = f"https://api.themoviedb.org/3/tv/1?api_key={SECRET}&language=zh-CN"


class _Collector(logging.Handler):
    """直接挂在 unisub logger 上收集日志文本，不依赖 caplog 的传播设置。"""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@pytest.fixture
def logs():
    """收集 unisub logger 在用例期间输出的全部文本。"""
    from app.core.logger import init_logger

    collector = _Collector()
    target = init_logger()
    target.addHandler(collector)
    try:
        yield collector.messages
    finally:
        target.removeHandler(collector)


@pytest.fixture
async def mocked_http():
    """把单例 HttpClient 的底层 httpx 客户端换成 MockTransport。"""
    http = AsyncHttpClient()
    original = http._client
    mock = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(404)))
    http._client = mock
    try:
        yield http
    finally:
        await mock.aclose()
        http._client = original


def test_strip_query_removes_secret():
    """query string 整体剥离，path 保留。"""
    assert strip_query(SECRET_URL) == "https://api.themoviedb.org/3/tv/1"


def test_strip_query_keeps_plain_url():
    """无 query 的 URL 原样返回。"""
    url = "http://192.168.31.10:8092/api/openapi/subscribe"
    assert strip_query(url) == url


def test_strip_query_handles_httpx_error_message():
    """httpx 异常消息里的 URL 同样被剥离。"""
    text = f"Client error '404 Not Found' for url '{SECRET_URL}'\nFor more information check: https://example.com/x"
    cleaned = strip_query(text)
    assert SECRET not in cleaned
    assert "api_key" not in cleaned


async def test_get_error_detail_is_redacted(mocked_http, logs):
    """get() 的 detail 与日志都不含密钥。"""
    result = await mocked_http.get(SECRET_URL)

    assert result["error"] == "HTTP 404"
    assert SECRET not in result["detail"]
    assert SECRET not in "\n".join(logs)
    assert "api_key" not in "\n".join(logs)


async def test_get_text_exception_is_redacted(mocked_http, logs):
    """get_text() 抛出的异常消息与日志都不含密钥。"""
    with pytest.raises(HttpRequestError) as exc_info:
        await mocked_http.get_text(SECRET_URL)

    assert SECRET not in str(exc_info.value)
    assert SECRET not in "\n".join(logs)


async def test_get_bytes_exception_is_redacted(mocked_http, logs):
    """get_bytes() 抛出的异常消息与日志都不含密钥。"""
    with pytest.raises(HttpRequestError) as exc_info:
        await mocked_http.get_bytes(SECRET_URL)

    assert SECRET not in str(exc_info.value)
    assert SECRET not in "\n".join(logs)
