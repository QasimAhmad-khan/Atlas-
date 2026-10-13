from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from atlaspipe.crawler.frontier_worker import FrontierWorker
from atlaspipe.worker_health import run_with_shutdown


async def test_shutdown_cancels_stuck_batch_within_drain_budget() -> None:
    cancelled = asyncio.Event()

    async def stuck(**_kwargs: object) -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    worker = AsyncMock(spec=FrontierWorker)
    worker.run_continuously.side_effect = stuck
    stop = asyncio.Event()
    stop.set()
    with pytest.raises(TimeoutError):
        await run_with_shutdown(worker, stop, drain_seconds=0.01, poll_seconds=0.01)
    assert cancelled.is_set()
