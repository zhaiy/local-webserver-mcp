"""Shared HTTP client and lifecycle management."""

from __future__ import annotations

import asyncio
import atexit
import contextlib
from typing import Any

import httpx

from mcp_web_server.config import DEFAULT_TIMEOUT, DEFAULT_USER_AGENT, HTTP_PROXY, HTTPS_PROXY


HTTP_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

HTTP_TRANSPORT = httpx.AsyncHTTPTransport(retries=2)
HTTP_PROXIES: dict[str, str] = {}
if HTTP_PROXY:
    HTTP_PROXIES["http://"] = HTTP_PROXY
if HTTPS_PROXY:
    HTTP_PROXIES["https://"] = HTTPS_PROXY

_HTTP_CLIENT_KWARGS: dict[str, Any] = {
    "transport": HTTP_TRANSPORT,
    "limits": httpx.Limits(max_keepalive_connections=10, max_connections=20),
    "headers": HTTP_HEADERS,
    "timeout": httpx.Timeout(DEFAULT_TIMEOUT, connect=10.0),
    "follow_redirects": True,
}
if HTTP_PROXIES:
    _HTTP_CLIENT_KWARGS["proxies"] = HTTP_PROXIES

HTTP_CLIENT = httpx.AsyncClient(**_HTTP_CLIENT_KWARGS)


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
