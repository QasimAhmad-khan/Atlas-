from __future__ import annotations

import asyncio
import os
import signal
import socket
from uuid import uuid4

from sqlalchemy import delete

from atlaspipe.config import get_settings
from atlaspipe.crawler.fetcher import AioHttpFetcher
from atlaspipe.crawler.frontier_worker import FrontierWorker
from atlaspipe.crawler.retry import RetryPolicy
from atlaspipe.db.models import WorkerHeartbeat
from atlaspipe.db.session import create_engine, create_session_factory
from atlaspipe.observability.logging import configure_logging
from atlaspipe.observability.telemetry import configure_tracing, start_worker_metrics
from atlaspipe.worker_health import heartbeat_loop, run_with_shutdown


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    configure_tracing(settings, "worker")
    owner = os.getenv("ATLASPIPE_WORKER_ID") or f"{socket.gethostname()}-{uuid4().hex[:8]}"
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)
    metrics_server = (
        start_worker_metrics(settings, engine) if settings.worker_metrics_port else None
    )
    graceful = False

    try:
        async with AioHttpFetcher(
            timeout_seconds=settings.request_timeout,
            user_agent=settings.user_agent,
            max_response_bytes=settings.max_response_bytes,
            allow_private_networks=settings.allow_private_networks,
        ) as fetcher:
            worker = FrontierWorker.with_session_factory(
                owner=owner,
                session_factory=session_factory,
                fetcher=fetcher,
                batch_size=settings.batch_size,
                lease_seconds=settings.frontier_lease_seconds,
                concurrency=settings.max_concurrency,
                per_domain_concurrency=settings.per_domain_concurrency,
                requests_per_second=settings.requests_per_second,
                retry_policy=RetryPolicy(max_retries=settings.max_retries),
            )
            heartbeat = asyncio.create_task(heartbeat_loop(engine, worker, owner, settings))
            running = asyncio.create_task(
                run_with_shutdown(
                    worker,
                    stop_event,
                    drain_seconds=settings.worker_drain_seconds,
                    poll_seconds=settings.frontier_poll_interval_seconds,
                )
            )
            try:
                await asyncio.wait({running, heartbeat}, return_when=asyncio.FIRST_COMPLETED)
                if heartbeat.done():
                    await heartbeat
                await running
                graceful = True
            finally:
                running.cancel()
                heartbeat.cancel()
                await asyncio.gather(running, heartbeat, return_exceptions=True)
    finally:
        if metrics_server is not None:
            await asyncio.to_thread(metrics_server.shutdown)
            metrics_server.server_close()
        if graceful:
            async with engine.begin() as connection:
                await connection.execute(
                    delete(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == owner)
                )
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
