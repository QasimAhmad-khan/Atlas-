from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class TokenBucketRateLimiter:
    def __init__(self, rate_per_second: float) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        self._rate = rate_per_second
        self._tokens = rate_per_second
        self._updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._updated_at
                self._tokens = min(self._rate, self._tokens + elapsed * self._rate)
                self._updated_at = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                wait_time = (1 - self._tokens) / self._rate
            await asyncio.sleep(wait_time)


class DomainConcurrencyLimiter:
    def __init__(self, per_domain_limit: int) -> None:
        if per_domain_limit <= 0:
            raise ValueError("per_domain_limit must be positive")
        self._per_domain_limit = per_domain_limit
        self._semaphores: defaultdict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(self._per_domain_limit)
        )

    @asynccontextmanager
    async def limit(self, domain: str) -> AsyncIterator[None]:
        semaphore = self._semaphores[domain]
        async with semaphore:
            yield
