"""HTTP-related MCP tools."""

from __future__ import annotations

import asyncio
import time as time_module
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from mcp_web_server.config import logger
from mcp_web_server.http_client import HTTP_CLIENT, HTTP_HEADERS, safe_request
from mcp_web_server.models import HttpResponse
from mcp_web_server.tools.common import error_response, handle_common_exception, success_response
from mcp_web_server.utils.rate_limit import HTTP_RATE_LIMITER
from mcp_web_server.utils.validation import ALLOWED_METHODS, validate_range, validate_url


async def http_request(
    url: str,
    method: str = "GET",
    headers: Optional[dict] = None,
    json_data: Optional[dict] = None,
    timeout: int = 30,
) -> dict[str, Any]:
    merged_headers = {**HTTP_HEADERS, **(headers or {})}
    start = time_module.perf_counter()
    logger.info("http_request called", extra={"method": method.upper(), "url": url})
    if not validate_url(url):
        return error_response("ValidationError", "url must be a valid http/https URL")
    if method.upper() not in ALLOWED_METHODS:
        return error_response("ValidationError", "method is not allowed")
    timeout_error = validate_range("timeout", timeout, 1, 120)
    if timeout_error:
        return error_response("ValidationError", timeout_error)
    try:
        await HTTP_RATE_LIMITER.acquire()
        logger.debug("HTTP %s %s", method.upper(), url)
        response = await safe_request(
            method=method.upper(),
            url=url,
            headers=merged_headers,
            json=json_data,
            timeout=timeout,
        )
        return success_response(
            HttpResponse(
                status_code=response.status_code,
                headers=dict(response.headers),
                body=response.text,
            ).model_dump()
        )
    except Exception as exc:
        return handle_common_exception("http_request", exc)
    finally:
        logger.info("http_request completed in %.2fs", time_module.perf_counter() - start)


async def fetch_json(url: str, timeout: int = 30) -> dict[str, Any]:
    start = time_module.perf_counter()
    logger.info("fetch_json called", extra={"url": url})
    if not validate_url(url):
        return error_response("ValidationError", "url must be a valid http/https URL")
    timeout_error = validate_range("timeout", timeout, 1, 120)
    if timeout_error:
        return error_response("ValidationError", timeout_error)
    try:
        await HTTP_RATE_LIMITER.acquire()
        logger.debug("HTTP GET %s", url)
        response = await safe_request("GET", url, timeout=timeout)
        response.raise_for_status()
        return success_response(response.json())
    except Exception as exc:
        return handle_common_exception("fetch_json", exc)
    finally:
        logger.info("fetch_json completed in %.2fs", time_module.perf_counter() - start)


async def batch_http_request(
    urls: list[str],
    method: str = "GET",
    headers: Optional[dict] = None,
    timeout: int = 30,
    max_concurrent: int = 5,
) -> dict[str, Any]:
    start = time_module.perf_counter()
    logger.info(
        "batch_http_request called",
        extra={"url_count": len(urls), "method": method.upper(), "max_concurrent": max_concurrent},
    )
    if method.upper() not in ALLOWED_METHODS:
        return error_response("ValidationError", "method is not allowed")
    timeout_error = validate_range("timeout", timeout, 1, 120)
    if timeout_error:
        return error_response("ValidationError", timeout_error)
    concurrency_error = validate_range("max_concurrent", max_concurrent, 1, 20)
    if concurrency_error:
        return error_response("ValidationError", concurrency_error)
    for url in urls:
        if not validate_url(url):
            return error_response("ValidationError", "all urls must be valid http/https URLs")
    semaphore = asyncio.Semaphore(max_concurrent)
    merged_headers = {**HTTP_HEADERS, **(headers or {})}

    async def _request_one(url: str) -> dict[str, Any]:
        async with semaphore:
            try:
                logger.debug("HTTP %s %s", method.upper(), url)
                response = await safe_request(
                    method=method.upper(),
                    url=url,
                    headers=merged_headers,
                    timeout=timeout,
                )
                response.raise_for_status()
                return {
                    "url": url,
                    "success": True,
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response.text,
                }
            except Exception as exc:
                return handle_common_exception("batch_http_request", exc) | {"url": url, "success": False}

    try:
        tasks = [_request_one(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return success_response(results)
    except Exception as exc:
        return handle_common_exception("batch_http_request", exc)
    finally:
        logger.info("batch_http_request completed in %.2fs", time_module.perf_counter() - start)


def register_http_tools(mcp: FastMCP) -> None:
    mcp.tool()(http_request)
    mcp.tool()(fetch_json)
    mcp.tool()(batch_http_request)
