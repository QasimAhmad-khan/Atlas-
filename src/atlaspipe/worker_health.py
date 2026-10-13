from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from atlaspipe.config import Settings, get_settings
from atlaspipe.crawler.frontier_worker import FrontierWorker
from atlaspipe.db.models import WorkerHeartbeat


def heartbeat_path() -> Path:
    return Path(
        os.getenv(
            "WORKER_HEALTH_FILE", str(Path(tempfile.gettempdir()) / "atlaspipe-worker-health")
        )
    )


async def heartbeat_loop(
    engine: AsyncEngine,
    worker: FrontierWorker,
    owner: str,
    settings: Settings,
) -> None:
    while True:
        async with engine.begin() as connection:
            statement = insert(WorkerHeartbeat).values(
                worker_id=owner,
                seen_at=func.now(),
                progress_at=worker.last_progress_at,
                release=settings.release,
            )
            await connection.execute(
                statement.on_conflict_do_update(
                    index_elements=[WorkerHeartbeat.worker_id],
                    set_={
                        "seen_at": func.now(),
                        "progress_at": worker.last_progress_at,
                        "release": settings.release,
                    },
                )
            )
        heartbeat_path().write_text(str(time.time()), encoding="utf-8")
        await asyncio.sleep(settings.worker_heartbeat_seconds)


async def run_with_shutdown(
    worker: FrontierWorker,
    stop: asyncio.Event,
    *,
    drain_seconds: float,
    poll_seconds: float,
) -> None:
    running = asyncio.create_task(
        worker.run_continuously(stop_event=stop, poll_interval_seconds=poll_seconds)
    )
    stopping = asyncio.create_task(stop.wait())
    try:
        await asyncio.wait({running, stopping}, return_when=asyncio.FIRST_COMPLETED)
        await asyncio.wait_for(running, timeout=drain_seconds)
    finally:
        running.cancel()
        stopping.cancel()
        await asyncio.gather(running, stopping, return_exceptions=True)


def main() -> None:
    try:
        age = time.time() - float(heartbeat_path().read_text(encoding="utf-8"))
        healthy = 0 <= age < get_settings().worker_stale_seconds
    except (OSError, ValueError):
        healthy = False
    raise SystemExit(0 if healthy else 1)


if __name__ == "__main__":
    main()
