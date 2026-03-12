from unittest.mock import AsyncMock, patch

import pytest

from mcp_web_server.server import web_search


@pytest.mark.asyncio
async def test_web_search_success() -> None:
    class FakeDDGS:
        def __enter__(self) -> "FakeDDGS":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
            return None

        def text(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return [
                {"title": "A", "href": "https://a.com", "body": "sa"},
                {"title": "B", "href": "https://b.com", "body": "sb"},
            ]

    with patch("mcp_web_server.tools.search.DDGS", FakeDDGS):
        with patch("mcp_web_server.tools.search.asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())):
            result = await web_search("python", num_results=2)

    assert result["success"] is True
    assert len(result["data"]) == 2
    assert result["data"][0]["url"] == "https://a.com"


@pytest.mark.asyncio
async def test_web_search_failure() -> None:
    class BrokenDDGS:
        def __enter__(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("search failed")

        def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
            return None

    with patch("mcp_web_server.tools.search.DDGS", BrokenDDGS):
        with patch("mcp_web_server.tools.search.asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())):
            result = await web_search("python")

    assert result["success"] is False
    assert result["error"] == "Exception"


@pytest.mark.asyncio
async def test_web_search_empty_result() -> None:
    class EmptyDDGS:
        def __enter__(self) -> "EmptyDDGS":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
            return None

        def text(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return []

    with patch("mcp_web_server.tools.search.DDGS", EmptyDDGS):
        with patch("mcp_web_server.tools.search.asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())):
            result = await web_search("python")

    assert result["success"] is True
    assert result["data"] == []
