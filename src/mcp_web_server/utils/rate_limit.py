"""Rate limiter utilities."""

from __future__ import annotations

import asyncio
import time as time_module

from mcp_web_server.config import RATE_LIMIT_EXTRACT, RATE_LIMIT_HTTP, RATE_LIMIT_SEARCH


class RateLimiter:
    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self.calls: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time_module.monotonic()
            self.calls = [t for t in self.calls if now - t < self.period]
            if len(self.calls) >= self.max_calls:
                sleep_time = self.period - (now - self.calls[0])
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                now = time_module.monotonic()
                self.calls = [t for t in self.calls if now - t < self.period]
            self.calls.append(time_module.monotonic())


SEARCH_RATE_LIMITER = RateLimiter(max_calls=RATE_LIMIT_SEARCH, period=60.0)
HTTP_RATE_LIMITER = RateLimiter(max_calls=RATE_LIMIT_HTTP, period=60.0)
EXTRACT_RATE_LIMITER = RateLimiter(max_calls=RATE_LIMIT_EXTRACT, period=60.0)
