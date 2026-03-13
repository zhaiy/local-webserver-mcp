"""Shared HTTP client and lifecycle management."""

from __future__ import annotations

import asyncio
import atexit
import contextlib
from typing import Any

import httpx

from mcp_web_server.config import DEFAULT_TIMEOUT, DEFAULT_USER_AGENT, HTTP_PROXY, HTTPS_PROXY
from mcp_web_server.utils.validation import validate_url


HTTP_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

HTTP_TRANSPORT = httpx.AsyncHTTPTransport(retries=2)
HTTP_MOUNTS: dict[str, httpx.AsyncHTTPTransport] = {}
if HTTP_PROXY:
    HTTP_MOUNTS["http://"] = httpx.AsyncHTTPTransport(proxy=HTTP_PROXY, retries=2)
if HTTPS_PROXY:
    HTTP_MOUNTS["https://"] = httpx.AsyncHTTPTransport(proxy=HTTPS_PROXY, retries=2)

_HTTP_CLIENT_KWARGS: dict[str, Any] = {
    "transport": HTTP_TRANSPORT,
    "limits": httpx.Limits(max_keepalive_connections=10, max_connections=20),
    "headers": HTTP_HEADERS,
    "timeout": httpx.Timeout(DEFAULT_TIMEOUT, connect=10.0),
    "follow_redirects": False,  # 禁用自动重定向，防止 SSRF 绕过
}
if HTTP_MOUNTS:
    _HTTP_CLIENT_KWARGS["mounts"] = HTTP_MOUNTS

HTTP_CLIENT = httpx.AsyncClient(**_HTTP_CLIENT_KWARGS)

# 最大重定向次数
MAX_REDIRECTS = 5


def _is_cross_origin(source: httpx.URL, target: httpx.URL) -> bool:
    """检查两个 URL 是否跨域（协议/主机/端口任一不同）。"""
    return (
        source.scheme != target.scheme
        or source.host != target.host
        or source.port != target.port
    )


def _strip_sensitive_headers_for_cross_origin(
    headers: dict[str, str] | httpx.Headers,
) -> dict[str, str]:
    """跨域重定向时移除敏感请求头，避免凭证泄露。"""
    sanitized_headers = dict(headers)
    for header_name in (
        "authorization",
        "proxy-authorization",
        "cookie",
        "x-api-key",
        "x-auth-token",
    ):
        sanitized_headers.pop(header_name, None)
        sanitized_headers.pop(header_name.title(), None)
        sanitized_headers.pop(header_name.upper(), None)
    return sanitized_headers


async def safe_request(
    method: str,
    url: str,
    **kwargs: Any,
) -> httpx.Response:
    """执行 HTTP 请求，手动处理重定向并二次验证 URL。

    禁用自动重定向后，此函数负责：
    1. 执行请求
    2. 遇到 3xx 响应时，验证 Location 头的 URL
    3. 验证通过则手动跟随重定向，最多 MAX_REDIRECTS 次

    Args:
        method: HTTP 方法
        url: 请求 URL
        **kwargs: 传递给 httpx.AsyncClient.request 的其他参数

    Returns:
        httpx.Response: 最终响应

    Raises:
        httpx.InvalidURL: 重定向目标 URL 不合法
        httpx.TooManyRedirects: 重定向次数超过限制
    """
    current_url = httpx.URL(url)
    request_method = method.upper()
    redirect_count = 0
    request_kwargs = dict(kwargs)

    while True:
        response = await HTTP_CLIENT.request(request_method, str(current_url), **request_kwargs)

        if not response.is_redirect:
            return response

        # 获取重定向目标
        location = response.headers.get("location")
        if not location:
            return response

        # 解析相对 URL 为绝对 URL
        redirect_target = response.url.join(location)
        current_url_str = str(redirect_target)

        # 二次验证重定向目标 URL
        if not validate_url(current_url_str):
            raise httpx.InvalidURL(f"重定向目标 URL 不合法: {current_url_str}")

        redirect_count += 1
        if redirect_count > MAX_REDIRECTS:
            raise httpx.TooManyRedirects(f"重定向次数超过限制: {MAX_REDIRECTS}")

        # 跨域重定向时，剥离敏感头，避免携带凭证到第三方域名
        if _is_cross_origin(response.url, redirect_target):
            headers = request_kwargs.get("headers")
            if isinstance(headers, (dict, httpx.Headers)):
                request_kwargs["headers"] = _strip_sensitive_headers_for_cross_origin(headers)

        # 按 RFC 处理重定向方法与请求体
        if response.status_code == 303 or (
            response.status_code in {301, 302} and request_method not in {"GET", "HEAD"}
        ):
            request_method = "GET"
            request_kwargs.pop("content", None)
            request_kwargs.pop("data", None)
            request_kwargs.pop("json", None)

        current_url = redirect_target


async def _close_http_client() -> None:
    if not HTTP_CLIENT.is_closed:
        await HTTP_CLIENT.aclose()


def _close_http_client_at_exit() -> None:
    if HTTP_CLIENT.is_closed:
        return
    try:
        asyncio.run(_close_http_client())
    except RuntimeError:
        with contextlib.suppress(RuntimeError):
            loop = asyncio.new_event_loop()
            loop.run_until_complete(_close_http_client())
            loop.close()


atexit.register(_close_http_client_at_exit)
