from __future__ import annotations

import asyncio

import pytest

from atlaspipe.crawler.rate_limiter import DomainConcurrencyLimiter
from atlaspipe.crawler.retry import RetryPolicy, should_retry_status


def test_retry_classifier_retries_transient_statuses_only() -> None:
    assert should_retry_status(429)
    assert should_retry_status(503)
    assert not should_retry_status(404)


def test_retry_policy_delay_grows() -> None:
    policy = RetryPolicy(jitter_seconds=0)
    assert policy.delay_for_attempt(2) > policy.delay_for_attempt(1)


@pytest.mark.asyncio
async def test_domain_concurrency_limiter_bounds_parallel_work() -> None:
    limiter = DomainConcurrencyLimiter(per_domain_limit=1)
    active = 0
    max_active = 0

    async def work() -> None:
        nonlocal active, max_active
        async with limiter.limit("example.com"):
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1

    await asyncio.gather(work(), work(), work())
    assert max_active == 1
