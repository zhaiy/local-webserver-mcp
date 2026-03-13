import pytest
from unittest.mock import patch

from mcp_web_server.server import batch_http_request, extract_webpage_content, fetch_json, http_request, web_search
from mcp_web_server.utils.validation import validate_url


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


def test_validate_url_rejects_loopback_ipv4() -> None:
    assert validate_url("http://127.0.0.1/") is False


def test_validate_url_rejects_private_ipv4() -> None:
    assert validate_url("http://10.0.0.1/api") is False


def test_validate_url_rejects_link_local_ipv4() -> None:
    assert validate_url("http://169.254.169.254/latest/meta-data") is False


def test_validate_url_rejects_ipv6_loopback() -> None:
    assert validate_url("http://[::1]/") is False


def test_validate_url_rejects_localhost_hostname() -> None:
    with patch(
        "mcp_web_server.utils.validation.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("127.0.0.1", 0))],
    ):
        assert validate_url("http://localhost/") is False


def test_validate_url_accepts_public_domain() -> None:
    with patch(
        "mcp_web_server.utils.validation.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("93.184.216.34", 0))],
    ):
        assert validate_url("https://www.example.com/") is True


def test_validate_url_rejects_non_http_scheme() -> None:
    assert validate_url("ftp://example.com/file.txt") is False


def test_validate_url_rejects_dns_resolution_failure() -> None:
    with patch(
        "mcp_web_server.utils.validation.socket.getaddrinfo",
        side_effect=OSError("dns failed"),
    ):
        assert validate_url("https://public.example/") is False
