"""
MCP Web Server - A local MCP server providing free web access capabilities.

Features:
- HTTP requests (GET/POST)
- Web search via DuckDuckGo (no API key required)
- Webpage content extraction
"""

import asyncio
import json
from typing import Any, Optional
from mcp.server.fastmcp import FastMCP
import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS

# Initialize the MCP server
mcp = FastMCP("Web Server")


# HTTP Client configuration
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _success_response(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data}


def _error_response(error_type: str, message: str) -> dict[str, Any]:
    return {"success": False, "error": error_type, "message": message}


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
        async with httpx.AsyncClient() as client:
            response = await client.request(
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
def web_search(
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
        List of search results with title, url, and snippet
    """
    try:
        results = []
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
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=HTTP_HEADERS, timeout=30)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove script, style, nav, header, footer elements
        for element in soup(["script", "style", "nav", "header", "footer", "noscript"]):
            element.decompose()

        # Extract title
        title = ""
        if soup.title:
            title = soup.title.string or ""

        # Extract main content
        main_content = []

        # Try to find main article content
        main_tag = soup.find("main") or soup.find("article") or soup.find("div", class_=["content", "article", "post"])

        if main_tag:
            content_tag = main_tag
        else:
            content_tag = soup.find("body") or soup

        # Extract paragraphs
        for p in content_tag.find_all("p", recursive=True):
            text = p.get_text(strip=True)
            if text and len(text) > 10:
                main_content.append(text)

        # Extract headings
        headings = []
        for h in content_tag.find_all(["h1", "h2", "h3"], recursive=True):
            text = h.get_text(strip=True)
            if text:
                headings.append(text)

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
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=HTTP_HEADERS, timeout=timeout)
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
