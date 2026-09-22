from __future__ import annotations

import asyncio
from collections.abc import Iterable


async def enqueue_bounded(urls: Iterable[str], queue: asyncio.Queue[str]) -> None:
    for url in urls:
        await queue.put(url)
