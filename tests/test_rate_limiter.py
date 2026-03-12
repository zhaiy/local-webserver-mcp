from unittest.mock import AsyncMock, patch

import pytest

from mcp_web_server.server import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_waits_when_limit_reached() -> None:
    limiter = RateLimiter(max_calls=1, period=10.0)
    monotonic_values = iter([0.0, 0.0, 1.0, 10.0, 10.0])
    sleep_mock = AsyncMock()

    with patch("mcp_web_server.utils.rate_limit.time_module.monotonic", side_effect=lambda: next(monotonic_values)):
        with patch("mcp_web_server.utils.rate_limit.asyncio.sleep", sleep_mock):
            await limiter.acquire()
            await limiter.acquire()

    sleep_mock.assert_awaited_once_with(9.0)


@pytest.mark.asyncio
async def test_rate_limiter_no_wait_under_limit() -> None:
    limiter = RateLimiter(max_calls=2, period=10.0)
    sleep_mock = AsyncMock()

    with patch("mcp_web_server.utils.rate_limit.asyncio.sleep", sleep_mock):
        await limiter.acquire()
        await limiter.acquire()

    sleep_mock.assert_not_awaited()
