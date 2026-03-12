"""Search-related MCP tools."""

from __future__ import annotations

import asyncio
import json
import time as time_module
from typing import Any

import httpx
from ddgs import DDGS
from mcp.server.fastmcp import FastMCP

from mcp_web_server.config import logger
from mcp_web_server.models import SearchResult
from mcp_web_server.tools.common import error_response, handle_common_exception, success_response
from mcp_web_server.tools.extract import _extract_webpage_content_impl
from mcp_web_server.utils.rate_limit import EXTRACT_RATE_LIMITER, SEARCH_RATE_LIMITER
from mcp_web_server.utils.validation import validate_range


async def _web_search_impl(
    query: str,
    num_results: int,
    region: str,
    time: str,
    apply_rate_limit: bool = True,
) -> list[dict[str, str]]:
    if apply_rate_limit:
        await SEARCH_RATE_LIMITER.acquire()

    def _search() -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        with DDGS() as ddgs:
            ddg_results = list(
                ddgs.text(
                    query,
                    region=region,
                    safesearch="off",
                    time=time,
                    max_results=num_results,
                )
            )
            for result in ddg_results:
                results.append(
                    SearchResult(
                        title=result.get("title", ""),
                        url=result.get("href", ""),
                        snippet=result.get("body", ""),
                    ).model_dump()
                )
        return results

    return await asyncio.to_thread(_search)


async def web_search(
    query: str,
    num_results: int = 10,
    region: str = "wt-wt",
    time: str = "y",
) -> dict[str, Any]:
    start = time_module.perf_counter()
    logger.info("web_search called", extra={"query": query, "num_results": num_results})
    num_results_error = validate_range("num_results", num_results, 1, 50)
    if num_results_error:
        return error_response("ValidationError", num_results_error)
    try:
        results = await _web_search_impl(
            query=query,
            num_results=num_results,
            region=region,
            time=time,
            apply_rate_limit=True,
        )
        return success_response(results)
    except Exception as exc:
        return handle_common_exception("web_search", exc)
    finally:
        logger.info("web_search completed in %.2fs", time_module.perf_counter() - start)


async def web_search_and_extract(
    query: str,
    num_results: int = 3,
    max_content_length: int = 5000,
    region: str = "wt-wt",
) -> dict[str, Any]:
    start = time_module.perf_counter()
    logger.info("web_search_and_extract called", extra={"query": query, "num_results": num_results})
    num_results_error = validate_range("num_results", num_results, 1, 50)
    if num_results_error:
        return error_response("ValidationError", num_results_error)
    max_length_error = validate_range("max_content_length", max_content_length, 100, 100000)
    if max_length_error:
        return error_response("ValidationError", max_length_error)

    try:
        await SEARCH_RATE_LIMITER.acquire()
        search_results = await _web_search_impl(
            query=query,
            num_results=num_results,
            region=region,
            time="y",
            apply_rate_limit=False,
        )
        search_results = search_results[:num_results]

        async def _extract_item(item: dict[str, str]) -> dict[str, Any]:
            url = item.get("url", "")
            try:
                extracted_data = await _extract_webpage_content_impl(
                    url=url,
                    include_links=False,
                    max_length=max_content_length,
                    apply_rate_limit=False,
                )
                extract_response: dict[str, Any] = {"success": True, "data": extracted_data}
            except Exception as exc:
                logger.error("extract_webpage_content failed", exc_info=True)
                if isinstance(exc, httpx.TimeoutException):
                    extract_response = error_response("TimeoutException", str(exc))
                elif isinstance(exc, httpx.ConnectError):
                    extract_response = error_response("ConnectError", str(exc))
                elif isinstance(exc, httpx.HTTPStatusError):
                    extract_response = error_response("HTTPStatusError", str(exc))
                elif isinstance(exc, json.JSONDecodeError):
                    extract_response = error_response("JSONDecodeError", str(exc))
                else:
                    extract_response = error_response(type(exc).__name__, str(exc))

            merged_item: dict[str, Any] = {
                "title": item.get("title", ""),
                "url": url,
                "snippet": item.get("snippet", ""),
            }
            if extract_response.get("success"):
                merged_item["content"] = extract_response.get("data", {}).get("content", "")
            else:
                merged_item["content"] = ""
                merged_item["extract_error"] = {
                    "error": extract_response.get("error", "Exception"),
                    "message": extract_response.get("message", "Unknown extraction error"),
                }
            return merged_item

        if search_results:
            await EXTRACT_RATE_LIMITER.acquire()
        tasks = [_extract_item(item) for item in search_results]
        extracted_results = await asyncio.gather(*tasks, return_exceptions=True)

        merged_results: list[dict[str, Any]] = []
        for item, extracted in zip(search_results, extracted_results):
            if isinstance(extracted, Exception):
                merged_results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("snippet", ""),
                        "content": "",
                        "extract_error": {
                            "error": type(extracted).__name__,
                            "message": str(extracted),
                        },
                    }
                )
            else:
                merged_results.append(extracted)

        return success_response({"query": query, "results": merged_results})
    except Exception as exc:
        return handle_common_exception("web_search_and_extract", exc)
    finally:
        logger.info("web_search_and_extract completed in %.2fs", time_module.perf_counter() - start)


def register_search_tools(mcp: FastMCP) -> None:
    mcp.tool()(web_search)
    mcp.tool()(web_search_and_extract)
