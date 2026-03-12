import pytest

from mcp_web_server.server import batch_http_request, extract_webpage_content, fetch_json, http_request, web_search


@pytest.mark.asyncio
async def test_http_request_rejects_invalid_url() -> None:
    result = await http_request("ftp://example.com")
    assert result["success"] is False
    assert result["error"] == "ValidationError"


@pytest.mark.asyncio
async def test_http_request_rejects_invalid_method() -> None:
    result = await http_request("https://example.com", method="TRACE")
    assert result["success"] is False
    assert result["error"] == "ValidationError"


@pytest.mark.asyncio
async def test_extract_rejects_invalid_max_length() -> None:
    result = await extract_webpage_content("https://example.com", max_length=10)
    assert result["success"] is False
    assert result["error"] == "ValidationError"


@pytest.mark.asyncio
async def test_fetch_json_rejects_invalid_timeout() -> None:
    result = await fetch_json("https://example.com/data.json", timeout=0)
    assert result["success"] is False
    assert result["error"] == "ValidationError"


@pytest.mark.asyncio
async def test_batch_http_request_rejects_invalid_max_concurrent() -> None:
    result = await batch_http_request(["https://example.com"], max_concurrent=0)
    assert result["success"] is False
    assert result["error"] == "ValidationError"


@pytest.mark.asyncio
async def test_web_search_rejects_invalid_num_results() -> None:
    result = await web_search("python", num_results=0)
    assert result["success"] is False
    assert result["error"] == "ValidationError"
