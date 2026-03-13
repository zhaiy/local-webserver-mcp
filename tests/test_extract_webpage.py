from unittest.mock import MagicMock

import httpx
import pytest

from mcp_web_server.server import extract_webpage_content


def _response_with_text(text: str) -> MagicMock:
    response = MagicMock()
    response.text = text
    response.raise_for_status.return_value = None
    return response


@pytest.mark.asyncio
async def test_extract_webpage_basic_content(
    mock_httpx_client: dict,
    sample_html_page: str,
) -> None:
    mock_httpx_client["extract"].return_value = _response_with_text(sample_html_page)

    result = await extract_webpage_content("https://example.com")

    assert result["success"] is True
    content = result["data"]["content"]
    assert "## Main Heading" in content
    assert "First paragraph with meaningful content." in content


@pytest.mark.asyncio
async def test_extract_webpage_include_links(
    mock_httpx_client: dict,
    sample_html_page: str,
) -> None:
    mock_httpx_client["extract"].return_value = _response_with_text(sample_html_page)

    result = await extract_webpage_content("https://example.com", include_links=True)

    assert result["success"] is True
    assert result["data"]["links"][0]["url"] == "https://example.com/docs"


@pytest.mark.asyncio
async def test_extract_webpage_max_length(mock_httpx_client: dict) -> None:
    html = "<html><body><p>" + ("x" * 1000) + "</p></body></html>"
    mock_httpx_client["extract"].return_value = _response_with_text(html)

    result = await extract_webpage_content("https://example.com", max_length=100)

    assert result["success"] is True
    assert result["data"]["content"].endswith("...")


@pytest.mark.asyncio
async def test_extract_webpage_non_html_content(mock_httpx_client: dict) -> None:
    mock_httpx_client["extract"].return_value = _response_with_text("plain text body only")

    result = await extract_webpage_content("https://example.com")

    assert result["success"] is True
    assert isinstance(result["data"]["content"], str)


@pytest.mark.asyncio
async def test_extract_webpage_timeout(mock_httpx_client: dict) -> None:
    mock_httpx_client["extract"].side_effect = httpx.TimeoutException("timeout")

    result = await extract_webpage_content("https://example.com")

    assert result["success"] is False
    assert result["error"] == "TimeoutException"


@pytest.mark.asyncio
async def test_extract_webpage_connect_error(mock_httpx_client: dict) -> None:
    mock_httpx_client["extract"].side_effect = httpx.ConnectError("connect failed")

    result = await extract_webpage_content("https://example.com")

    assert result["success"] is False
    assert result["error"] == "ConnectError"
