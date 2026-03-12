"""
MCP Web Server - A local MCP server providing free web access capabilities.

Features:
- HTTP requests (GET/POST)
- Web search via DuckDuckGo (no API key required)
- Webpage content extraction
"""

import asyncio
import atexit
import base64
import json
import logging
import os
import time as time_module
from typing import Any, Optional
from urllib.parse import urlparse
from mcp.server.fastmcp import FastMCP
import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag
from ddgs import DDGS
from mcp_web_server.models import ErrorResponse, HttpResponse, SearchResult, SuccessResponse, WebLink, WebpageContent

try:
    from playwright.async_api import async_playwright

    HAS_PLAYWRIGHT = True
except ImportError:
    async_playwright = None
    HAS_PLAYWRIGHT = False

# Initialize the MCP server
mcp = FastMCP("Web Server")

LOG_LEVEL = os.getenv("MCP_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("mcp-web-server")


# HTTP Client configuration
DEFAULT_USER_AGENT = os.getenv(
    "MCP_USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)
DEFAULT_TIMEOUT = float(os.getenv("MCP_DEFAULT_TIMEOUT", "30"))

HTTP_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

HTTP_TRANSPORT = httpx.AsyncHTTPTransport(retries=2)
HTTP_PROXIES: dict[str, str] = {}
if os.getenv("MCP_HTTP_PROXY"):
    HTTP_PROXIES["http://"] = os.environ["MCP_HTTP_PROXY"]
if os.getenv("MCP_HTTPS_PROXY"):
    HTTP_PROXIES["https://"] = os.environ["MCP_HTTPS_PROXY"]

_HTTP_CLIENT_KWARGS: dict[str, Any] = {
    "transport": HTTP_TRANSPORT,
    "limits": httpx.Limits(max_keepalive_connections=10, max_connections=20),
    "headers": HTTP_HEADERS,
    "timeout": httpx.Timeout(DEFAULT_TIMEOUT, connect=10.0),
    "follow_redirects": True,
}
if HTTP_PROXIES:
    _HTTP_CLIENT_KWARGS["proxies"] = HTTP_PROXIES

HTTP_CLIENT = httpx.AsyncClient(
    **_HTTP_CLIENT_KWARGS,
)


class RateLimiter:
    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self.calls: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time_module.monotonic()
            self.calls = [t for t in self.calls if now - t < self.period]
            if len(self.calls) >= self.max_calls:
                sleep_time = self.period - (now - self.calls[0])
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                now = time_module.monotonic()
                self.calls = [t for t in self.calls if now - t < self.period]
            self.calls.append(time_module.monotonic())


SEARCH_RATE_LIMITER = RateLimiter(max_calls=int(os.getenv("MCP_RATE_LIMIT_SEARCH", "5")), period=60.0)
HTTP_RATE_LIMITER = RateLimiter(max_calls=int(os.getenv("MCP_RATE_LIMIT_HTTP", "30")), period=60.0)
EXTRACT_RATE_LIMITER = RateLimiter(max_calls=int(os.getenv("MCP_RATE_LIMIT_EXTRACT", "10")), period=60.0)


async def _close_http_client() -> None:
    if not HTTP_CLIENT.is_closed:
        await HTTP_CLIENT.aclose()


def _close_http_client_at_exit() -> None:
    if HTTP_CLIENT.is_closed:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_close_http_client())
    else:
        loop.create_task(_close_http_client())


atexit.register(_close_http_client_at_exit)

ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}


def _success_response(data: Any) -> dict[str, Any]:
    return SuccessResponse(data=data).model_dump()


def _error_response(error_type: str, message: str) -> dict[str, Any]:
    return ErrorResponse(error=error_type, message=message).model_dump()


def validate_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _validate_range(name: str, value: int, min_value: int, max_value: int) -> dict[str, Any] | None:
    if not (min_value <= value <= max_value):
        return _error_response(
            "ValidationError",
            f"{name} must be between {min_value} and {max_value}",
        )
    return None


def _extract_content_blocks(content_tag: Tag) -> tuple[list[str], list[str]]:
    blocks: list[str] = []
    headings: list[str] = []
    processed_ids: set[int] = set()

    for element in content_tag.descendants:
        if not isinstance(element, Tag):
            continue
        if id(element) in processed_ids:
            continue
        if any(id(parent) in processed_ids for parent in element.parents if isinstance(parent, Tag)):
            continue

        if element.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            text = element.get_text(" ", strip=True)
            if text:
                headings.append(text)
                blocks.append(f"## {text}")
                processed_ids.add(id(element))
            continue

        if element.name == "p":
            text = element.get_text(" ", strip=True)
            if text:
                blocks.append(text)
                processed_ids.add(id(element))
            continue

        if element.name in {"ul", "ol"}:
            items = [
                li.get_text(" ", strip=True)
                for li in element.find_all("li")
                if li.get_text(" ", strip=True)
            ]
            for item in items:
                blocks.append(f"- {item}")
            processed_ids.add(id(element))
            continue

        if element.name == "table":
            table_rows: list[str] = []
            for tr in element.find_all("tr"):
                cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
                cells = [cell for cell in cells if cell]
                if cells:
                    table_rows.append(" | ".join(cells))
            if table_rows:
                blocks.extend(table_rows)
            processed_ids.add(id(element))
            continue

        if element.name == "pre":
            code_text = element.get_text("\n", strip=True)
            if code_text:
                blocks.append(f"```\n{code_text}\n```")
            processed_ids.add(id(element))
            continue

        if element.name == "code":
            if isinstance(element.parent, Tag) and element.parent.name == "pre":
                continue
            code_text = element.get_text(" ", strip=True)
            if code_text:
                blocks.append(f"```\n{code_text}\n```")
                processed_ids.add(id(element))
            continue

        if element.name == "blockquote":
            quote_text = element.get_text(" ", strip=True)
            if quote_text:
                blocks.append(f"> {quote_text}")
                processed_ids.add(id(element))

    return blocks, headings


@mcp.tool()
async def http_request(
    url: str,
    method: str = "GET",
    headers: Optional[dict] = None,
    json_data: Optional[dict] = None,
    timeout: int = 30,
) -> dict:
    """
    Make an HTTP request to a URL.

    Args:
        url: The URL to request
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        headers: Optional custom headers
        json_data: Optional JSON data for POST/PUT requests
        timeout: Request timeout in seconds

    Returns:
        Dictionary containing status_code, headers, and body
    """
    merged_headers = {**HTTP_HEADERS, **(headers or {})}
    start = time_module.perf_counter()
    logger.info("http_request called", extra={"method": method.upper(), "url": url})
    if not validate_url(url):
        return _error_response("ValidationError", "url must be a valid http/https URL")
    if method.upper() not in ALLOWED_METHODS:
        return _error_response("ValidationError", "method is not allowed")
    timeout_error = _validate_range("timeout", timeout, 1, 120)
    if timeout_error:
        return timeout_error
    try:
        await HTTP_RATE_LIMITER.acquire()
        logger.debug("HTTP %s %s", method.upper(), url)
        response = await HTTP_CLIENT.request(
            method=method.upper(),
            url=url,
            headers=merged_headers,
            json=json_data,
            timeout=timeout,
        )
        response.raise_for_status()

        return _success_response(
            HttpResponse(
                status_code=response.status_code,
                headers=dict(response.headers),
                body=response.text,
            ).model_dump()
        )
    except httpx.TimeoutException as exc:
        logger.error("http_request failed", exc_info=True)
        return _error_response("TimeoutException", str(exc))
    except httpx.ConnectError as exc:
        logger.error("http_request failed", exc_info=True)
        return _error_response("ConnectError", str(exc))
    except httpx.HTTPStatusError as exc:
        logger.error("http_request failed", exc_info=True)
        return _error_response("HTTPStatusError", str(exc))
    except json.JSONDecodeError as exc:
        logger.error("http_request failed", exc_info=True)
        return _error_response("JSONDecodeError", str(exc))
    except Exception as exc:
        logger.error("http_request failed", exc_info=True)
        return _error_response("Exception", str(exc))
    finally:
        logger.info("http_request completed in %.2fs", time_module.perf_counter() - start)


@mcp.tool()
async def web_search(
    query: str,
    num_results: int = 10,
    region: str = "wt-wt",
    time: str = "y",
) -> dict[str, Any]:
    """
    Search the web using DuckDuckGo (no API key required).

    Args:
        query: Search query string
        num_results: Maximum number of results to return (default: 10)
        region: Region code (default: wt-wt for worldwide)
        time: Time filter - d (day), w (week), m (month), y (year)

    Returns:
        Unified response containing search results with title, url, and snippet
    """
    start = time_module.perf_counter()
    logger.info("web_search called", extra={"query": query, "num_results": num_results})
    num_results_error = _validate_range("num_results", num_results, 1, 50)
    if num_results_error:
        return num_results_error
    try:
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

        results = await asyncio.to_thread(_search)
        return _success_response(results)
    except httpx.TimeoutException as exc:
        logger.error("web_search failed", exc_info=True)
        return _error_response("TimeoutException", str(exc))
    except httpx.ConnectError as exc:
        logger.error("web_search failed", exc_info=True)
        return _error_response("ConnectError", str(exc))
    except httpx.HTTPStatusError as exc:
        logger.error("web_search failed", exc_info=True)
        return _error_response("HTTPStatusError", str(exc))
    except json.JSONDecodeError as exc:
        logger.error("web_search failed", exc_info=True)
        return _error_response("JSONDecodeError", str(exc))
    except Exception as exc:
        logger.error("web_search failed", exc_info=True)
        return _error_response("Exception", str(exc))
    finally:
        logger.info("web_search completed in %.2fs", time_module.perf_counter() - start)


@mcp.tool()
async def extract_webpage_content(
    url: str,
    include_links: bool = False,
    max_length: int = 10000,
) -> dict:
    """
    Extract readable content from a webpage.

    Args:
        url: The URL of the webpage to extract
        include_links: Whether to include links in the output
        max_length: Maximum characters in the extracted content

    Returns:
        Dictionary containing title, text content, and optionally links
    """
    start = time_module.perf_counter()
    logger.info("extract_webpage_content called", extra={"url": url})
    if not validate_url(url):
        return _error_response("ValidationError", "url must be a valid http/https URL")
    max_length_error = _validate_range("max_length", max_length, 100, 100000)
    if max_length_error:
        return max_length_error
    try:
        await EXTRACT_RATE_LIMITER.acquire()
        logger.debug("HTTP GET %s", url)
        response = await HTTP_CLIENT.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove script, style, nav, header, footer elements
        for element in soup(["script", "style", "nav", "header", "footer", "noscript"]):
            element.decompose()

        # Extract title
        title = ""
        if soup.title:
            title = soup.title.string or ""

        # Try to find main article content
        main_tag = soup.find("main") or soup.find("article") or soup.find("div", class_=["content", "article", "post"])

        if main_tag:
            content_tag = main_tag
        else:
            content_tag = soup.find("body") or soup

        # Extract headings + paragraphs + lists + tables + code + blockquote in DOM order.
        main_content, headings = _extract_content_blocks(content_tag)

        # Extract links if requested
        links = []
        if include_links:
            for a in content_tag.find_all("a", href=True):
                text = a.get_text(strip=True)
                href = a["href"]
                if text and href.startswith("http"):
                    links.append({"text": text, "url": href})

        # Combine text content
        text_content = "\n\n".join(main_content)
        if len(text_content) > max_length:
            text_content = text_content[:max_length] + "..."

        webpage_data: dict[str, Any] = {
            "url": url,
            "title": title,
            "content": text_content,
            "headings": headings[:20],  # Limit headings
        }

        if include_links:
            webpage_data["links"] = [
                WebLink(text=link["text"], url=link["url"]) for link in links[:50]
            ]

        return _success_response(WebpageContent(**webpage_data).model_dump())
    except httpx.TimeoutException as exc:
        logger.error("extract_webpage_content failed", exc_info=True)
        return _error_response("TimeoutException", str(exc))
    except httpx.ConnectError as exc:
        logger.error("extract_webpage_content failed", exc_info=True)
        return _error_response("ConnectError", str(exc))
    except httpx.HTTPStatusError as exc:
        logger.error("extract_webpage_content failed", exc_info=True)
        return _error_response("HTTPStatusError", str(exc))
    except json.JSONDecodeError as exc:
        logger.error("extract_webpage_content failed", exc_info=True)
        return _error_response("JSONDecodeError", str(exc))
    except Exception as exc:
        logger.error("extract_webpage_content failed", exc_info=True)
        return _error_response("Exception", str(exc))
    finally:
        logger.info("extract_webpage_content completed in %.2fs", time_module.perf_counter() - start)


@mcp.tool()
async def fetch_json(url: str, timeout: int = 30) -> dict:
    """
    Fetch and parse JSON data from a URL.

    Args:
        url: The URL to fetch JSON from
        timeout: Request timeout in seconds

    Returns:
        Parsed JSON data as a dictionary
    """
    start = time_module.perf_counter()
    logger.info("fetch_json called", extra={"url": url})
    if not validate_url(url):
        return _error_response("ValidationError", "url must be a valid http/https URL")
    timeout_error = _validate_range("timeout", timeout, 1, 120)
    if timeout_error:
        return timeout_error
    try:
        logger.debug("HTTP GET %s", url)
        response = await HTTP_CLIENT.get(url, timeout=timeout)
        response.raise_for_status()
        return _success_response(response.json())
    except httpx.TimeoutException as exc:
        logger.error("fetch_json failed", exc_info=True)
        return _error_response("TimeoutException", str(exc))
    except httpx.ConnectError as exc:
        logger.error("fetch_json failed", exc_info=True)
        return _error_response("ConnectError", str(exc))
    except httpx.HTTPStatusError as exc:
        logger.error("fetch_json failed", exc_info=True)
        return _error_response("HTTPStatusError", str(exc))
    except json.JSONDecodeError as exc:
        logger.error("fetch_json failed", exc_info=True)
        return _error_response("JSONDecodeError", str(exc))
    except Exception as exc:
        logger.error("fetch_json failed", exc_info=True)
        return _error_response("Exception", str(exc))
    finally:
        logger.info("fetch_json completed in %.2fs", time_module.perf_counter() - start)


@mcp.tool()
async def web_search_and_extract(
    query: str,
    num_results: int = 3,
    max_content_length: int = 5000,
    region: str = "wt-wt",
) -> dict[str, Any]:
    """
    Search and extract content for top search results.

    Args:
        query: Search query string
        num_results: Number of results to search/extract
        max_content_length: Max content length for each extracted page
        region: DuckDuckGo region code

    Returns:
        Unified response with query and extracted result list
    """
    start = time_module.perf_counter()
    logger.info("web_search_and_extract called", extra={"query": query, "num_results": num_results})
    num_results_error = _validate_range("num_results", num_results, 1, 50)
    if num_results_error:
        return num_results_error
    max_length_error = _validate_range("max_content_length", max_content_length, 100, 100000)
    if max_length_error:
        return max_length_error
    try:
        search_response = await web_search(
            query=query,
            num_results=num_results,
            region=region,
        )
        if not search_response.get("success"):
            return search_response

        search_results = search_response.get("data", [])[:num_results]

        async def _extract_item(item: dict[str, str]) -> dict[str, Any]:
            url = item.get("url", "")
            extract_response = await extract_webpage_content(url=url, max_length=max_content_length)

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

        return _success_response({"query": query, "results": merged_results})
    except httpx.TimeoutException as exc:
        logger.error("web_search_and_extract failed", exc_info=True)
        return _error_response("TimeoutException", str(exc))
    except httpx.ConnectError as exc:
        logger.error("web_search_and_extract failed", exc_info=True)
        return _error_response("ConnectError", str(exc))
    except httpx.HTTPStatusError as exc:
        logger.error("web_search_and_extract failed", exc_info=True)
        return _error_response("HTTPStatusError", str(exc))
    except json.JSONDecodeError as exc:
        logger.error("web_search_and_extract failed", exc_info=True)
        return _error_response("JSONDecodeError", str(exc))
    except Exception as exc:
        logger.error("web_search_and_extract failed", exc_info=True)
        return _error_response("Exception", str(exc))
    finally:
        logger.info("web_search_and_extract completed in %.2fs", time_module.perf_counter() - start)


@mcp.tool()
async def batch_http_request(
    urls: list[str],
    method: str = "GET",
    headers: Optional[dict] = None,
    timeout: int = 30,
    max_concurrent: int = 5,
) -> dict[str, Any]:
    """
    Make concurrent HTTP requests for multiple URLs.

    Args:
        urls: URL list
        method: HTTP method
        headers: Optional request headers
        timeout: Timeout in seconds
        max_concurrent: Max concurrent requests

    Returns:
        Unified response containing per-URL results
    """
    start = time_module.perf_counter()
    logger.info(
        "batch_http_request called",
        extra={"url_count": len(urls), "method": method.upper(), "max_concurrent": max_concurrent},
    )
    if method.upper() not in ALLOWED_METHODS:
        return _error_response("ValidationError", "method is not allowed")
    timeout_error = _validate_range("timeout", timeout, 1, 120)
    if timeout_error:
        return timeout_error
    concurrency_error = _validate_range("max_concurrent", max_concurrent, 1, 20)
    if concurrency_error:
        return concurrency_error
    for url in urls:
        if not validate_url(url):
            return _error_response("ValidationError", "all urls must be valid http/https URLs")
    semaphore = asyncio.Semaphore(max_concurrent)
    merged_headers = {**HTTP_HEADERS, **(headers or {})}

    async def _request_one(url: str) -> dict[str, Any]:
        async with semaphore:
            try:
                logger.debug("HTTP %s %s", method.upper(), url)
                response = await HTTP_CLIENT.request(
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
            except httpx.TimeoutException as exc:
                return {"url": url, "success": False, "error": "TimeoutException", "message": str(exc)}
            except httpx.ConnectError as exc:
                return {"url": url, "success": False, "error": "ConnectError", "message": str(exc)}
            except httpx.HTTPStatusError as exc:
                return {"url": url, "success": False, "error": "HTTPStatusError", "message": str(exc)}
            except Exception as exc:
                return {"url": url, "success": False, "error": "Exception", "message": str(exc)}

    try:
        tasks = [_request_one(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return _success_response(results)
    except Exception as exc:
        logger.error("batch_http_request failed", exc_info=True)
        return _error_response("Exception", str(exc))
    finally:
        logger.info("batch_http_request completed in %.2fs", time_module.perf_counter() - start)


if HAS_PLAYWRIGHT:

    @mcp.tool()
    async def screenshot_webpage(
        url: str,
        full_page: bool = False,
        width: int = 1280,
        height: int = 720,
    ) -> dict[str, Any]:
        """
        Capture webpage screenshot and return base64 image bytes.

        Requires playwright:
            uv pip install -e ".[screenshot]" && playwright install chromium
        """
        start = time_module.perf_counter()
        logger.info("screenshot_webpage called", extra={"url": url})
        try:
            assert async_playwright is not None
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page(viewport={"width": width, "height": height})
                await page.goto(url, wait_until="networkidle", timeout=30000)
                image_bytes = await page.screenshot(full_page=full_page, type="png")
                await browser.close()

            return _success_response(
                {
                    "url": url,
                    "image_base64": base64.b64encode(image_bytes).decode("utf-8"),
                    "width": width,
                    "height": height,
                }
            )
        except httpx.TimeoutException as exc:
            logger.error("screenshot_webpage failed", exc_info=True)
            return _error_response("TimeoutException", str(exc))
        except httpx.ConnectError as exc:
            logger.error("screenshot_webpage failed", exc_info=True)
            return _error_response("ConnectError", str(exc))
        except httpx.HTTPStatusError as exc:
            logger.error("screenshot_webpage failed", exc_info=True)
            return _error_response("HTTPStatusError", str(exc))
        except json.JSONDecodeError as exc:
            logger.error("screenshot_webpage failed", exc_info=True)
            return _error_response("JSONDecodeError", str(exc))
        except Exception as exc:
            logger.error("screenshot_webpage failed", exc_info=True)
            return _error_response("Exception", str(exc))
        finally:
            logger.info("screenshot_webpage completed in %.2fs", time_module.perf_counter() - start)


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
