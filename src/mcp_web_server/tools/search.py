"""Search-related MCP tools."""

from __future__ import annotations

import asyncio
import json
import time as time_module
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS
from mcp.server.fastmcp import FastMCP

from mcp_web_server.config import BING_DOMAIN, SEARCH_ENGINE, SUPPORTED_SEARCH_ENGINES, logger
from mcp_web_server.http_client import HTTP_CLIENT
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

    engine = SEARCH_ENGINE.strip().lower()
    if engine == "duckduckgo":
        return await _search_duckduckgo(query=query, num_results=num_results, region=region, time=time)
    if engine == "bing":
        return await _search_bing(query=query, num_results=num_results, region=region, time=time)
    if engine == "baidu":
        return await _search_baidu(query=query, num_results=num_results, region=region, time=time)
    raise ValueError(
        f"Unsupported search engine: {engine}. Supported engines: {', '.join(SUPPORTED_SEARCH_ENGINES)}"
    )


def _build_search_result(title: str, url: str, snippet: str) -> dict[str, str]:
    return SearchResult(title=title, url=url, snippet=snippet).model_dump()


def _search_duckduckgo_sync(query: str, num_results: int, region: str, time: str) -> list[dict[str, str]]:
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
                _build_search_result(
                    title=result.get("title", ""),
                    url=result.get("href", ""),
                    snippet=result.get("body", ""),
                )
            )
    return results


async def _search_duckduckgo(query: str, num_results: int, region: str, time: str) -> list[dict[str, str]]:
    return await asyncio.to_thread(_search_duckduckgo_sync, query, num_results, region, time)


def _extract_first_text(node: Any, selectors: list[str]) -> str:
    for selector in selectors:
        matched = node.select_one(selector)
        if matched:
            return matched.get_text(" ", strip=True)
    return ""


def _normalize_bing_base_url(domain: str) -> str:
    normalized = domain.strip()
    if not normalized:
        normalized = "www.bing.com"
    if not normalized.startswith(("http://", "https://")):
        normalized = f"https://{normalized}"
    return normalized.rstrip("/")


def _region_to_country_code(region: str) -> str | None:
    # Examples: wt-wt, us-en, cn-zh
    primary = (region or "").split("-", 1)[0].lower().strip()
    if len(primary) == 2 and primary != "wt":
        return primary
    return None


def _bing_time_filter(time: str) -> str | None:
    return {
        "d": "+filterui:age-lt24h",
        "w": "+filterui:age-lt7d",
        "m": "+filterui:age-lt30d",
        "y": "+filterui:age-lt365d",
    }.get((time or "").lower().strip())


def _looks_like_challenge_page(soup: BeautifulSoup) -> bool:
    page_text = soup.get_text(" ", strip=True).lower()
    challenge_keywords = (
        "captcha",
        "verify you are human",
        "unusual traffic",
        "人机验证",
        "验证码",
        "安全验证",
    )
    return any(keyword in page_text for keyword in challenge_keywords)


def _is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


async def _search_bing(query: str, num_results: int, region: str, time: str) -> list[dict[str, str]]:
    params: dict[str, Any] = {"q": query, "count": max(num_results, 1)}
    country_code = _region_to_country_code(region)
    if country_code:
        params["cc"] = country_code
    time_filter = _bing_time_filter(time)
    if time_filter:
        params["qft"] = time_filter

    response = await HTTP_CLIENT.get(
        f"{_normalize_bing_base_url(BING_DOMAIN)}/search",
        params=params,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for item in soup.select("li.b_algo"):
        link_node = item.select_one("h2 a") or item.select_one("a")
        if not link_node:
            continue
        title = link_node.get_text(" ", strip=True)
        url = (link_node.get("href") or "").strip()
        snippet = _extract_first_text(item, ["div.b_caption p", "p"])
        if not title or not url or url in seen_urls:
            continue
        seen_urls.add(url)
        results.append(_build_search_result(title=title, url=url, snippet=snippet))
        if len(results) >= num_results:
            break
    if not results and _looks_like_challenge_page(soup):
        logger.warning("bing search returned challenge page; query=%s", query)
    return results


async def _resolve_baidu_result_url(raw_url: str, node: Any) -> str:
    # Prefer explicit landing URL if present.
    for attr in ("data-landurl", "mu", "data-url"):
        candidate = (node.get(attr) or "").strip()
        if _is_http_url(candidate):
            return candidate

    # Fallback: follow baidu redirect to get actual target URL.
    if not raw_url.startswith(("http://www.baidu.com/link?", "https://www.baidu.com/link?")):
        return raw_url

    try:
        head_response = await HTTP_CLIENT.head(raw_url, timeout=10.0, follow_redirects=True)
        resolved_url = str(head_response.url)
        if _is_http_url(resolved_url) and "baidu.com/link?" not in resolved_url:
            return resolved_url
    except Exception:
        logger.debug("failed to resolve baidu url via HEAD: %s", raw_url, exc_info=True)

    try:
        get_response = await HTTP_CLIENT.get(raw_url, timeout=10.0, follow_redirects=True)
        resolved_url = str(get_response.url)
        if _is_http_url(resolved_url) and "baidu.com/link?" not in resolved_url:
            return resolved_url
    except Exception:
        logger.debug("failed to resolve baidu url via GET: %s", raw_url, exc_info=True)

    return raw_url


async def _search_baidu(query: str, num_results: int, region: str, time: str) -> list[dict[str, str]]:
    if (region or "").strip().lower() != "wt-wt":
        logger.warning("baidu search currently ignores region=%s", region)
    if (time or "").strip().lower() not in {"", "y"}:
        logger.warning("baidu search currently ignores time=%s", time)

    response = await HTTP_CLIENT.get(
        "https://www.baidu.com/s",
        params={"wd": query, "rn": max(num_results, 1)},
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for item in soup.select("div.result, div.c-container"):
        link_node = item.select_one("h3 a") or item.select_one("a")
        if not link_node:
            continue
        title = link_node.get_text(" ", strip=True)
        raw_url = (link_node.get("href") or "").strip()
        url = await _resolve_baidu_result_url(raw_url, link_node)
        if not title or not url or url in seen_urls:
            continue
        seen_urls.add(url)
        snippet = _extract_first_text(
            item,
            [
                "div.c-abstract",
                "div[class*='content-right']",
                "div.c-span-last",
                "p",
            ],
        )
        results.append(_build_search_result(title=title, url=url, snippet=snippet))
        if len(results) >= num_results:
            break
    if not results and _looks_like_challenge_page(soup):
        logger.warning("baidu search returned challenge page; query=%s", query)
    return results


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
    except ValueError as exc:
        return error_response("ValidationError", str(exc))
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
    except ValueError as exc:
        return error_response("ValidationError", str(exc))
    except Exception as exc:
        return handle_common_exception("web_search_and_extract", exc)
    finally:
        logger.info("web_search_and_extract completed in %.2fs", time_module.perf_counter() - start)


def register_search_tools(mcp: FastMCP) -> None:
    mcp.tool()(web_search)
    mcp.tool()(web_search_and_extract)
