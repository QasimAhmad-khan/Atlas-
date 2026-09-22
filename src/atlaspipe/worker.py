from __future__ import annotations

import asyncio
import os
import signal
import socket
from uuid import uuid4

from atlaspipe.config import get_settings
from atlaspipe.crawler.fetcher import AioHttpFetcher
from atlaspipe.crawler.frontier_worker import FrontierWorker
from atlaspipe.db.session import create_engine, create_session_factory
from atlaspipe.observability.logging import configure_logging


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    owner = os.getenv("ATLASPIPE_WORKER_ID") or f"{socket.gethostname()}-{uuid4().hex[:8]}"
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    try:
        async with AioHttpFetcher(
            timeout_seconds=settings.request_timeout,
            user_agent=settings.user_agent,
            max_response_bytes=settings.max_response_bytes,
        ) as fetcher:
            worker = FrontierWorker.with_session_factory(
                owner=owner,
                session_factory=session_factory,
                fetcher=fetcher,
                batch_size=settings.batch_size,
                lease_seconds=settings.frontier_lease_seconds,
                concurrency=settings.max_concurrency,
            )
            await worker.run_continuously(
                stop_event=stop_event,
                poll_interval_seconds=settings.frontier_poll_interval_seconds,
            )
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(run_worker())


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_args: stop_event.set())


if __name__ == "__main__":
    main()
