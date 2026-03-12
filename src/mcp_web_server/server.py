"""
MCP Web Server - A local MCP server providing free web access capabilities.

Features:
- HTTP requests (GET/POST)
- Web search via DuckDuckGo (no API key required)
- Webpage content extraction
"""

import asyncio
import atexit
import json
from typing import Any, Optional
from mcp.server.fastmcp import FastMCP
import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag
from ddgs import DDGS

# Initialize the MCP server
mcp = FastMCP("Web Server")


# HTTP Client configuration
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

HTTP_TRANSPORT = httpx.AsyncHTTPTransport(retries=2)

HTTP_CLIENT = httpx.AsyncClient(
    transport=HTTP_TRANSPORT,
    limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
    headers=HTTP_HEADERS,
    timeout=httpx.Timeout(30.0, connect=10.0),
    follow_redirects=True,
)


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


def _success_response(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data}


def _error_response(error_type: str, message: str) -> dict[str, Any]:
    return {"success": False, "error": error_type, "message": message}


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
    try:
        response = await HTTP_CLIENT.request(
            method=method.upper(),
            url=url,
            headers=merged_headers,
            json=json_data,
            timeout=timeout,
        )
        response.raise_for_status()

        return _success_response(
            {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response.text,
            }
        )
    except httpx.TimeoutException as exc:
        return _error_response("TimeoutException", str(exc))
    except httpx.ConnectError as exc:
        return _error_response("ConnectError", str(exc))
    except httpx.HTTPStatusError as exc:
        return _error_response("HTTPStatusError", str(exc))
    except json.JSONDecodeError as exc:
        return _error_response("JSONDecodeError", str(exc))
    except Exception as exc:
        return _error_response("Exception", str(exc))


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
    try:
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
                        {
                            "title": result.get("title", ""),
                            "url": result.get("href", ""),
                            "snippet": result.get("body", ""),
                        }
                    )
            return results

        results = await asyncio.to_thread(_search)
        return _success_response(results)
    except httpx.TimeoutException as exc:
        return _error_response("TimeoutException", str(exc))
    except httpx.ConnectError as exc:
        return _error_response("ConnectError", str(exc))
    except httpx.HTTPStatusError as exc:
        return _error_response("HTTPStatusError", str(exc))
    except json.JSONDecodeError as exc:
        return _error_response("JSONDecodeError", str(exc))
    except Exception as exc:
        return _error_response("Exception", str(exc))


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
    try:
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

        result = {
            "url": url,
            "title": title,
            "content": text_content,
            "headings": headings[:20],  # Limit headings
        }

        if include_links:
            result["links"] = links[:50]  # Limit links

        return _success_response(result)
    except httpx.TimeoutException as exc:
        return _error_response("TimeoutException", str(exc))
    except httpx.ConnectError as exc:
        return _error_response("ConnectError", str(exc))
    except httpx.HTTPStatusError as exc:
        return _error_response("HTTPStatusError", str(exc))
    except json.JSONDecodeError as exc:
        return _error_response("JSONDecodeError", str(exc))
    except Exception as exc:
        return _error_response("Exception", str(exc))


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
    try:
        response = await HTTP_CLIENT.get(url, timeout=timeout)
        response.raise_for_status()
        return _success_response(response.json())
    except httpx.TimeoutException as exc:
        return _error_response("TimeoutException", str(exc))
    except httpx.ConnectError as exc:
        return _error_response("ConnectError", str(exc))
    except httpx.HTTPStatusError as exc:
        return _error_response("HTTPStatusError", str(exc))
    except json.JSONDecodeError as exc:
        return _error_response("JSONDecodeError", str(exc))
    except Exception as exc:
        return _error_response("Exception", str(exc))


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
