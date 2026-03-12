"""Webpage content extraction tool."""

from __future__ import annotations

import time as time_module
from typing import Any

from bs4 import BeautifulSoup
from bs4.element import Tag
from mcp.server.fastmcp import FastMCP

from mcp_web_server.config import logger
from mcp_web_server.http_client import HTTP_CLIENT
from mcp_web_server.models import WebLink, WebpageContent
from mcp_web_server.tools.common import error_response, handle_common_exception, success_response
from mcp_web_server.utils.rate_limit import EXTRACT_RATE_LIMITER
from mcp_web_server.utils.validation import validate_range, validate_url


def _extract_content_blocks(content_tag: Tag) -> tuple[list[str], list[str]]:
    blocks: list[str] = []
    headings: list[str] = []

    def _consume_block(element: Tag) -> bool:
        if element.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            text = element.get_text(" ", strip=True)
            if text:
                headings.append(text)
                blocks.append(f"## {text}")
            return True
        if element.name == "p":
            text = element.get_text(" ", strip=True)
            if text:
                blocks.append(text)
            return True
        if element.name in {"ul", "ol"}:
            items = [
                li.get_text(" ", strip=True)
                for li in element.find_all("li")
                if li.get_text(" ", strip=True)
            ]
            for item in items:
                blocks.append(f"- {item}")
            return True
        if element.name == "table":
            table_rows: list[str] = []
            for tr in element.find_all("tr"):
                cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
                cells = [cell for cell in cells if cell]
                if cells:
                    table_rows.append(" | ".join(cells))
            if table_rows:
                blocks.extend(table_rows)
            return True
        if element.name == "pre":
            code_text = element.get_text("\n", strip=True)
            if code_text:
                blocks.append(f"```\n{code_text}\n```")
            return True
        if element.name == "code":
            if isinstance(element.parent, Tag) and element.parent.name == "pre":
                return False
            code_text = element.get_text(" ", strip=True)
            if code_text:
                blocks.append(f"```\n{code_text}\n```")
            return True
        if element.name == "blockquote":
            quote_text = element.get_text(" ", strip=True)
            if quote_text:
                blocks.append(f"> {quote_text}")
            return True
        return False

    def _walk(node: Tag) -> None:
        for child in node.children:
            if not isinstance(child, Tag):
                continue
            if _consume_block(child):
                continue
            _walk(child)

    _walk(content_tag)
    return blocks, headings


async def _extract_webpage_content_impl(
    url: str,
    include_links: bool,
    max_length: int,
    apply_rate_limit: bool = True,
) -> dict[str, Any]:
    if apply_rate_limit:
        await EXTRACT_RATE_LIMITER.acquire()
    logger.debug("HTTP GET %s", url)
    response = await HTTP_CLIENT.get(url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    for element in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        element.decompose()

    title = soup.title.string if soup.title and soup.title.string else ""
    main_tag = soup.find("main") or soup.find("article") or soup.find("div", class_=["content", "article", "post"])
    content_tag = main_tag if main_tag else soup.find("body") or soup

    main_content, headings = _extract_content_blocks(content_tag)
    links = []
    if include_links:
        for a in content_tag.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a["href"]
            if text and href.startswith("http"):
                links.append({"text": text, "url": href})

    text_content = "\n\n".join(main_content)
    if len(text_content) > max_length:
        text_content = text_content[:max_length] + "..."

    webpage_data: dict[str, Any] = {
        "url": url,
        "title": title,
        "content": text_content,
        "headings": headings[:20],
    }
    if include_links:
        webpage_data["links"] = [WebLink(text=link["text"], url=link["url"]) for link in links[:50]]
    return WebpageContent(**webpage_data).model_dump()


async def extract_webpage_content(
    url: str,
    include_links: bool = False,
    max_length: int = 10000,
) -> dict[str, Any]:
    start = time_module.perf_counter()
    logger.info("extract_webpage_content called", extra={"url": url})
    if not validate_url(url):
        return error_response("ValidationError", "url must be a valid http/https URL")
    max_length_error = validate_range("max_length", max_length, 100, 100000)
    if max_length_error:
        return error_response("ValidationError", max_length_error)
    try:
        data = await _extract_webpage_content_impl(
            url=url,
            include_links=include_links,
            max_length=max_length,
            apply_rate_limit=True,
        )
        return success_response(data)
    except Exception as exc:
        return handle_common_exception("extract_webpage_content", exc)
    finally:
        logger.info("extract_webpage_content completed in %.2fs", time_module.perf_counter() - start)


def register_extract_tools(mcp: FastMCP) -> None:
    mcp.tool()(extract_webpage_content)
