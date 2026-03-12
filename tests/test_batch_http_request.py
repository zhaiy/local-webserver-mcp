from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mcp_web_server.server import batch_http_request


@pytest.mark.asyncio
async def test_batch_http_request_empty_url_list() -> None:
    result = await batch_http_request([])
    assert result["success"] is True
    assert result["data"] == []


@pytest.mark.asyncio
async def test_batch_http_request_all_timeout() -> None:
    with patch(
        "mcp_web_server.server.HTTP_CLIENT.request",
        new=AsyncMock(side_effect=httpx.TimeoutException("timeout")),
    ):
        result = await batch_http_request(
            ["https://a.example", "https://b.example"],
            max_concurrent=2,
        )

    assert result["success"] is True
    assert len(result["data"]) == 2
    assert all(item["success"] is False for item in result["data"])
    assert all(item["error"] == "TimeoutException" for item in result["data"])


@pytest.mark.asyncio
async def test_batch_http_request_partial_success_partial_failure() -> None:
    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.headers = {"content-type": "text/plain"}
    ok_response.text = "ok"
    ok_response.raise_for_status.return_value = None

    request = httpx.Request("GET", "https://bad.example")
    bad_raw = httpx.Response(500, request=request)
    bad_response = MagicMock()
    bad_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "bad status",
        request=request,
        response=bad_raw,
    )

    async def mock_request(*args, **kwargs):  # type: ignore[no-untyped-def]
        if kwargs.get("url") == "https://ok.example":
            return ok_response
        return bad_response

    with patch("mcp_web_server.server.HTTP_CLIENT.request", new=AsyncMock(side_effect=mock_request)):
        result = await batch_http_request(["https://ok.example", "https://bad.example"])

    assert result["success"] is True
    assert result["data"][0]["success"] is True
    assert result["data"][1]["success"] is False
    assert result["data"][1]["error"] == "HTTPStatusError"
