from unittest.mock import AsyncMock, patch

import httpx
import pytest

from mcp_web_server.http_client import safe_request


@pytest.mark.asyncio
async def test_safe_request_strips_sensitive_headers_on_cross_origin_redirect() -> None:
    initial_request = httpx.Request("GET", "https://source.example/start")
    redirect_response = httpx.Response(
        302,
        headers={"location": "https://target.example/final"},
        request=initial_request,
    )
    final_response = httpx.Response(200, request=httpx.Request("GET", "https://target.example/final"))

    mock_request = AsyncMock(side_effect=[redirect_response, final_response])
    with patch("mcp_web_server.http_client.HTTP_CLIENT.request", new=mock_request):
        with patch("mcp_web_server.http_client.validate_url", return_value=True):
            response = await safe_request(
                "GET",
                "https://source.example/start",
                headers={
                    "Authorization": "Bearer token",
                    "Cookie": "session=abc",
                    "X-Test": "ok",
                },
            )

    assert response.status_code == 200
    second_call_headers = mock_request.await_args_list[1].kwargs["headers"]
    assert "Authorization" not in second_call_headers
    assert "Cookie" not in second_call_headers
    assert second_call_headers["X-Test"] == "ok"


@pytest.mark.asyncio
async def test_safe_request_keeps_headers_on_same_origin_redirect() -> None:
    initial_request = httpx.Request("GET", "https://source.example/start")
    redirect_response = httpx.Response(
        302,
        headers={"location": "/final"},
        request=initial_request,
    )
    final_response = httpx.Response(200, request=httpx.Request("GET", "https://source.example/final"))

    mock_request = AsyncMock(side_effect=[redirect_response, final_response])
    with patch("mcp_web_server.http_client.HTTP_CLIENT.request", new=mock_request):
        with patch("mcp_web_server.http_client.validate_url", return_value=True):
            response = await safe_request(
                "GET",
                "https://source.example/start",
                headers={"Authorization": "Bearer token", "X-Test": "ok"},
            )

    assert response.status_code == 200
    second_call_headers = mock_request.await_args_list[1].kwargs["headers"]
    assert second_call_headers["Authorization"] == "Bearer token"
    assert second_call_headers["X-Test"] == "ok"
