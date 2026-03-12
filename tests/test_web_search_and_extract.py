from unittest.mock import AsyncMock, patch

import httpx
import pytest

from mcp_web_server.server import web_search_and_extract


@pytest.mark.asyncio
async def test_web_search_and_extract_no_search_results() -> None:
    with patch(
        "mcp_web_server.tools.search._web_search_impl",
        new=AsyncMock(return_value=[]),
    ):
        result = await web_search_and_extract("query", num_results=3)

    assert result["success"] is True
    assert result["data"]["query"] == "query"
    assert result["data"]["results"] == []


@pytest.mark.asyncio
async def test_web_search_and_extract_all_extract_failed() -> None:
    search_data = [
        {"title": "A", "url": "https://a.example", "snippet": "sa"},
        {"title": "B", "url": "https://b.example", "snippet": "sb"},
    ]

    with patch(
        "mcp_web_server.tools.search._web_search_impl",
        new=AsyncMock(return_value=search_data),
    ):
        request = httpx.Request("GET", "https://a.example")
        response = httpx.Response(404, request=request)
        with patch(
            "mcp_web_server.tools.search._extract_webpage_content_impl",
            new=AsyncMock(side_effect=httpx.HTTPStatusError("404", request=request, response=response)),
        ):
            result = await web_search_and_extract("query", num_results=2)

    assert result["success"] is True
    assert len(result["data"]["results"]) == 2
    assert result["data"]["results"][0]["content"] == ""
    assert result["data"]["results"][0]["extract_error"]["error"] == "HTTPStatusError"
    assert result["data"]["results"][1]["content"] == ""
    assert result["data"]["results"][1]["extract_error"]["error"] == "HTTPStatusError"


@pytest.mark.asyncio
async def test_web_search_and_extract_single_extract_exception() -> None:
    search_data = [{"title": "A", "url": "https://a.example", "snippet": "sa"}]

    async def mock_extract(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    with patch(
        "mcp_web_server.tools.search._web_search_impl",
        new=AsyncMock(return_value=search_data),
    ):
        with patch("mcp_web_server.tools.search._extract_webpage_content_impl", new=mock_extract):
            result = await web_search_and_extract("query", num_results=1)

    assert result["success"] is True
    first = result["data"]["results"][0]
    assert first["content"] == ""
    assert first["extract_error"]["error"] == "RuntimeError"
    assert first["extract_error"]["message"] == "boom"


@pytest.mark.asyncio
async def test_web_search_and_extract_uses_single_limit_per_stage() -> None:
    search_data = [
        {"title": "A", "url": "https://a.example", "snippet": "sa"},
        {"title": "B", "url": "https://b.example", "snippet": "sb"},
    ]
    search_acquire = AsyncMock()
    extract_acquire = AsyncMock()

    with patch("mcp_web_server.tools.search.SEARCH_RATE_LIMITER.acquire", search_acquire):
        with patch("mcp_web_server.tools.search.EXTRACT_RATE_LIMITER.acquire", extract_acquire):
            with patch("mcp_web_server.tools.search._web_search_impl", new=AsyncMock(return_value=search_data)):
                with patch(
                    "mcp_web_server.tools.search._extract_webpage_content_impl",
                    new=AsyncMock(return_value={"url": "u", "title": "", "content": "c", "headings": []}),
                ) as extract_impl:
                    result = await web_search_and_extract("query", num_results=2)

    assert result["success"] is True
    search_acquire.assert_awaited_once()
    extract_acquire.assert_awaited_once()
    assert extract_impl.await_count == 2
