"""MCP Web Server - modularized registration entrypoint."""

from mcp.server.fastmcp import FastMCP

from mcp_web_server.http_client import HTTP_CLIENT, HTTP_HEADERS
from mcp_web_server.tools import (
    HAS_PLAYWRIGHT,
    _extract_webpage_content_impl,
    _web_search_impl,
    batch_http_request,
    extract_webpage_content,
    fetch_json,
    http_request,
    register_extract_tools,
    register_http_tools,
    register_screenshot_tools,
    register_search_tools,
    screenshot_webpage,
    web_search,
    web_search_and_extract,
)
from mcp_web_server.utils import (
    ALLOWED_METHODS,
    EXTRACT_RATE_LIMITER,
    HTTP_RATE_LIMITER,
    SEARCH_RATE_LIMITER,
    RateLimiter,
    validate_range,
    validate_url,
)


mcp = FastMCP("Web Server")
register_http_tools(mcp)
register_search_tools(mcp)
register_extract_tools(mcp)
register_screenshot_tools(mcp)


def main() -> None:
    mcp.run()


__all__ = [
    "mcp",
    "main",
    "http_request",
    "fetch_json",
    "batch_http_request",
    "web_search",
    "web_search_and_extract",
    "extract_webpage_content",
    "screenshot_webpage",
    "HTTP_CLIENT",
    "HTTP_HEADERS",
    "SEARCH_RATE_LIMITER",
    "HTTP_RATE_LIMITER",
    "EXTRACT_RATE_LIMITER",
    "ALLOWED_METHODS",
    "RateLimiter",
    "validate_url",
    "validate_range",
    "_web_search_impl",
    "_extract_webpage_content_impl",
    "HAS_PLAYWRIGHT",
]


if __name__ == "__main__":
    main()
