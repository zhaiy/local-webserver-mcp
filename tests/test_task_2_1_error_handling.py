import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mcp_web_server.server import (
    extract_webpage_content,
    fetch_json,
    http_request,
    web_search,
    web_search_and_extract,
)


@pytest.mark.asyncio
async def test_http_request_success_response_shape() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.text = '{"ok": true}'
    mock_response.raise_for_status.return_value = None

    with patch("mcp_web_server.server.HTTP_CLIENT.request", new=AsyncMock(return_value=mock_response)):
        result = await http_request("https://example.com")

    assert result["success"] is True
    assert result["data"]["status_code"] == 200
    assert result["data"]["body"] == '{"ok": true}'


@pytest.mark.asyncio
async def test_web_search_error_response_shape() -> None:
    with patch("mcp_web_server.server.DDGS", side_effect=RuntimeError("boom")):
        result = await web_search("python")

    assert result == {
        "success": False,
        "error": "Exception",
        "message": "boom",
    }


@pytest.mark.asyncio
async def test_web_search_uses_to_thread() -> None:
    expected_data = [{"title": "t", "url": "u", "snippet": "s"}]
    to_thread_mock = AsyncMock(return_value=expected_data)
    with patch("mcp_web_server.server.asyncio.to_thread", to_thread_mock):
        result = await web_search("python")

    to_thread_mock.assert_awaited_once()
    assert result["success"] is True
    assert result["data"] == expected_data


@pytest.mark.asyncio
async def test_extract_webpage_content_http_status_error() -> None:
    request = httpx.Request("GET", "https://example.com")
    response = httpx.Response(500, request=request)
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "server error",
        request=request,
        response=response,
    )

    with patch("mcp_web_server.server.HTTP_CLIENT.get", new=AsyncMock(return_value=mock_response)):
        result = await extract_webpage_content("https://example.com")

    assert result["success"] is False
    assert result["error"] == "HTTPStatusError"


@pytest.mark.asyncio
async def test_fetch_json_json_decode_error() -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.side_effect = json.JSONDecodeError("bad json", "x", 0)

    with patch("mcp_web_server.server.HTTP_CLIENT.get", new=AsyncMock(return_value=mock_response)):
        result = await fetch_json("https://example.com")

    assert result["success"] is False
    assert result["error"] == "JSONDecodeError"


@pytest.mark.asyncio
async def test_extract_webpage_content_supports_rich_tags_in_dom_order() -> None:
    html = """
    <html>
      <head><title>Example</title></head>
      <body>
        <main>
          <h1>Heading One</h1>
          <p>First paragraph.</p>
          <ul><li>Item A</li><li>Item B</li></ul>
          <blockquote>Quoted text</blockquote>
          <table><tr><th>K</th><th>V</th></tr><tr><td>a</td><td>1</td></tr></table>
          <pre><code>print("hi")</code></pre>
        </main>
      </body>
    </html>
    """
    mock_response = MagicMock()
    mock_response.text = html
    mock_response.raise_for_status.return_value = None

    with patch("mcp_web_server.server.HTTP_CLIENT.get", new=AsyncMock(return_value=mock_response)):
        result = await extract_webpage_content("https://example.com")

    assert result["success"] is True
    content = result["data"]["content"]
    assert "## Heading One" in content
    assert "First paragraph." in content
    assert "- Item A" in content
    assert "> Quoted text" in content
    assert "K | V" in content
    assert "```\nprint(\"hi\")\n```" in content
    assert content.index("## Heading One") < content.index("First paragraph.")


@pytest.mark.asyncio
async def test_web_search_and_extract_merges_content() -> None:
    search_data = [
        {"title": "A", "url": "https://a.com", "snippet": "sa"},
        {"title": "B", "url": "https://b.com", "snippet": "sb"},
    ]

    async def mock_extract(url: str, include_links: bool = False, max_length: int = 10000) -> dict:
        if "a.com" in url:
            return {"success": True, "data": {"content": "content-a"}}
        return {"success": False, "error": "HTTPStatusError", "message": "404"}

    with patch(
        "mcp_web_server.server.web_search",
        new=AsyncMock(return_value={"success": True, "data": search_data}),
    ):
        with patch("mcp_web_server.server.extract_webpage_content", new=mock_extract):
            result = await web_search_and_extract("query", num_results=2)

    assert result["success"] is True
    results = result["data"]["results"]
    assert results[0]["content"] == "content-a"
    assert results[1]["content"] == ""
    assert results[1]["extract_error"]["error"] == "HTTPStatusError"
