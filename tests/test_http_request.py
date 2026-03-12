from unittest.mock import MagicMock

import httpx
import pytest

from mcp_web_server.server import http_request


@pytest.mark.asyncio
async def test_http_request_success(mock_httpx_client: dict) -> None:
    response = MagicMock()
    response.status_code = 200
    response.headers = {"content-type": "application/json"}
    response.text = '{"ok": true}'
    response.raise_for_status.return_value = None
    mock_httpx_client["request"].return_value = response

    result = await http_request("https://example.com")

    assert result["success"] is True
    assert result["data"]["status_code"] == 200


@pytest.mark.asyncio
async def test_http_request_timeout(mock_httpx_client: dict) -> None:
    mock_httpx_client["request"].side_effect = httpx.TimeoutException("timeout")

    result = await http_request("https://example.com")

    assert result["success"] is False
    assert result["error"] == "TimeoutException"


@pytest.mark.asyncio
async def test_http_request_connect_error(mock_httpx_client: dict) -> None:
    mock_httpx_client["request"].side_effect = httpx.ConnectError("connect failed")

    result = await http_request("https://example.com")

    assert result["success"] is False
    assert result["error"] == "ConnectError"


@pytest.mark.asyncio
async def test_http_request_large_body(mock_httpx_client: dict) -> None:
    response = MagicMock()
    response.status_code = 200
    response.headers = {}
    response.text = "x" * 20000
    response.raise_for_status.return_value = None
    mock_httpx_client["request"].return_value = response

    result = await http_request("https://example.com")

    assert result["success"] is True
    assert len(result["data"]["body"]) == 20000


@pytest.mark.asyncio
async def test_http_request_non_2xx_returns_response_body(mock_httpx_client: dict) -> None:
    response = MagicMock()
    response.status_code = 404
    response.headers = {"content-type": "application/json"}
    response.text = '{"error":"not found"}'
    mock_httpx_client["request"].return_value = response

    result = await http_request("https://example.com/missing")

    assert result["success"] is True
    assert result["data"]["status_code"] == 404
    assert result["data"]["body"] == '{"error":"not found"}'
