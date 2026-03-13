import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mcp_web_server.server import fetch_json


def _json_response(data: dict) -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = data
    return response


@pytest.mark.asyncio
async def test_fetch_json_success(mock_httpx_client: dict) -> None:
    mock_httpx_client["http"].return_value = _json_response({"ok": True})

    result = await fetch_json("https://example.com/data.json")

    assert result["success"] is True
    assert result["data"]["ok"] is True


@pytest.mark.asyncio
async def test_fetch_json_timeout(mock_httpx_client: dict) -> None:
    mock_httpx_client["http"].side_effect = httpx.TimeoutException("timeout")

    result = await fetch_json("https://example.com/data.json")

    assert result["success"] is False
    assert result["error"] == "TimeoutException"


@pytest.mark.asyncio
async def test_fetch_json_connect_error(mock_httpx_client: dict) -> None:
    mock_httpx_client["http"].side_effect = httpx.ConnectError("connect failed")

    result = await fetch_json("https://example.com/data.json")

    assert result["success"] is False
    assert result["error"] == "ConnectError"


@pytest.mark.asyncio
async def test_fetch_json_invalid_json(mock_httpx_client: dict) -> None:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.side_effect = json.JSONDecodeError("bad json", "x", 0)
    mock_httpx_client["http"].return_value = response

    result = await fetch_json("https://example.com/data.json")

    assert result["success"] is False
    assert result["error"] == "JSONDecodeError"


@pytest.mark.asyncio
async def test_fetch_json_empty_object(mock_httpx_client: dict) -> None:
    mock_httpx_client["http"].return_value = _json_response({})

    result = await fetch_json("https://example.com/data.json")

    assert result["success"] is True
    assert result["data"] == {}


@pytest.mark.asyncio
async def test_fetch_json_applies_http_rate_limit(mock_httpx_client: dict) -> None:
    mock_httpx_client["http"].return_value = _json_response({"ok": True})
    acquire_mock = AsyncMock()

    with patch("mcp_web_server.tools.http.HTTP_RATE_LIMITER.acquire", acquire_mock):
        result = await fetch_json("https://example.com/data.json")

    assert result["success"] is True
    acquire_mock.assert_awaited_once()
