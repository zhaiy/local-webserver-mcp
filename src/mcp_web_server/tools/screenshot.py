"""Optional screenshot MCP tool powered by Playwright."""

from __future__ import annotations

import base64
import time as time_module
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_web_server.config import logger
from mcp_web_server.tools.common import error_response, success_response
from mcp_web_server.utils.rate_limit import EXTRACT_RATE_LIMITER
from mcp_web_server.utils.validation import validate_range, validate_url

try:
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright

    HAS_PLAYWRIGHT = True
except ImportError:
    async_playwright = None
    PlaywrightError = None
    PlaywrightTimeoutError = None
    HAS_PLAYWRIGHT = False


async def screenshot_webpage(
    url: str,
    full_page: bool = False,
    width: int = 1280,
    height: int = 720,
) -> dict[str, Any]:
    start = time_module.perf_counter()
    logger.info("screenshot_webpage called", extra={"url": url})
    if not validate_url(url):
        return error_response("ValidationError", "url must be a valid http/https URL")
    width_error = validate_range("width", width, 320, 7680)
    if width_error:
        return error_response("ValidationError", width_error)
    height_error = validate_range("height", height, 240, 4320)
    if height_error:
        return error_response("ValidationError", height_error)
    try:
        await EXTRACT_RATE_LIMITER.acquire()
        assert async_playwright is not None
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": width, "height": height})
            await page.goto(url, wait_until="networkidle", timeout=30000)
            image_bytes = await page.screenshot(full_page=full_page, type="png")
            await browser.close()
        return success_response(
            {
                "url": url,
                "image_base64": base64.b64encode(image_bytes).decode("utf-8"),
                "width": width,
                "height": height,
            }
        )
    except PlaywrightTimeoutError as exc:  # type: ignore[misc]
        logger.error("screenshot_webpage failed", exc_info=True)
        return error_response("TimeoutError", str(exc))
    except PlaywrightError as exc:  # type: ignore[misc]
        logger.error("screenshot_webpage failed", exc_info=True)
        return error_response("PlaywrightError", str(exc))
    except Exception as exc:
        logger.error("screenshot_webpage failed", exc_info=True)
        return error_response("Exception", str(exc))
    finally:
        logger.info("screenshot_webpage completed in %.2fs", time_module.perf_counter() - start)


def register_screenshot_tools(mcp: FastMCP) -> None:
    if HAS_PLAYWRIGHT:
        mcp.tool()(screenshot_webpage)
