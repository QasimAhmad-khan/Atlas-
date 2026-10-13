from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from collections.abc import AsyncIterator
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from aiohttp import web
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import TimeoutError as PoolTimeout

from atlaspipe.api.app import create_app
from atlaspipe.config import Settings
from atlaspipe.crawler.fetcher import AioHttpFetcher
from atlaspipe.crawler.frontier_worker import FrontierWorker
from atlaspipe.crawler.retry import RetryPolicy
from atlaspipe.db.models import CrawlFrontierItem, CrawlJob, Page
from atlaspipe.db.repositories import SqlAlchemyRepository
from atlaspipe.db.session import create_engine, create_session_factory
from atlaspipe.worker_health import run_with_shutdown

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="dedicated PostgreSQL required"
)


def evidence(name: str, data: dict[str, object]) -> None:
    directory = Path("artifacts/reliability")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.json").write_text(
        json.dumps(
            {
                "environment": "local Windows/POSIX fixture; not AWS",
                "timestamp": datetime.now(UTC).isoformat(),
                **data,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


@pytest_asyncio.fixture
async def fixture_server() -> AsyncIterator[str]:
    async def response(request: web.Request) -> web.Response:
        kind = request.match_info["kind"]
        if kind == "slow":
            await asyncio.sleep(0.2)
        if kind == "redirect":
            raise web.HTTPFound("http://169.254.169.254/latest/meta-data/")
        code = int(kind) if kind.isdigit() else 200
        return web.Response(
            status=code,
            text="<title>controlled fixture</title>",
            content_type="text/html",
            headers={"Retry-After": "0"},
        )

    app = web.Application()
    app.router.add_get("/{kind}/{run}", response)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    server = site._server
    assert server is not None
    port = server.sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        await runner.cleanup()


@pytest.mark.parametrize("point", ["after_fetch", "after_persist", "after_commit"])
async def test_actual_process_crash_at_persistence_boundary(
    point: str, fixture_server: str, tmp_path: Path
) -> None:
    settings = Settings(database_url=os.environ["DATABASE_URL"])
    engine = create_engine(settings)
    sessions = create_session_factory(engine)
    url = f"{fixture_server}/ok/{uuid4().hex}"
    async with sessions() as session:
        repo = SqlAlchemyRepository(session)
        job = await repo.create_job([url])
        await repo.schedule_frontier_urls(job_id=job.id, urls=[url], max_attempts=3)
        await session.commit()
    marker = tmp_path / "boundary"
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "scripts/fault_worker.py",
        "--point",
        point,
        "--marker",
        str(marker),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )  # noqa: S603
    try:
        for _ in range(300):
            if marker.exists() or process.returncode is not None:
                break
            await asyncio.sleep(0.05)
        assert marker.exists(), f"worker did not reach {point}"
        async with sessions() as session:
            before = await session.scalar(
                select(func.count()).select_from(Page).where(Page.normalized_url == url)
            )
        assert before == (1 if point == "after_commit" else 0)
        killed_at = time.monotonic()
        process.kill()
        await asyncio.wait_for(process.wait(), 5)
        async with AioHttpFetcher(
            timeout_seconds=2,
            user_agent="AtlasFixture",
            max_response_bytes=4096,
            allow_private_networks=True,
        ) as fetcher:
            worker = FrontierWorker.with_session_factory(
                owner="recovery-fixture",
                session_factory=sessions,
                fetcher=fetcher,
                batch_size=1,
                lease_seconds=2,
                concurrency=1,
            )
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                await worker.run_once()
                async with sessions() as session:
                    stats = await SqlAlchemyRepository(session).frontier_stats(job_id=job.id)
                if stats.complete == 1:
                    break
                await asyncio.sleep(0.1)
        async with sessions() as session:
            pages = await session.scalar(
                select(func.count()).select_from(Page).where(Page.normalized_url == url)
            )
            attempts = await session.scalar(
                select(CrawlFrontierItem.attempt_count).where(CrawlFrontierItem.job_id == job.id)
            )
        assert stats.complete == 1 and stats.pending == 0 and stats.leased == 0
        assert pages == 1
        assert attempts == (1 if point == "after_commit" else 2)
        evidence(
            point,
            {
                "passed": True,
                "page_count_before_kill": before,
                "logical_records_after_recovery": pages,
                "attempts": attempts,
                "frontier": asdict(stats),
                "recovery_seconds": time.monotonic() - killed_at,
                "trigger": "actual child process kill at controlled transaction boundary",
            },
        )
    finally:
        if process.returncode is None:
            process.kill()
            await asyncio.wait_for(process.wait(), 5)
        async with sessions() as session:
            await session.execute(delete(CrawlJob).where(CrawlJob.id == job.id))
            await session.execute(delete(Page).where(Page.normalized_url == url))
            await session.commit()
        await engine.dispose()


@pytest.mark.parametrize("kind", ["429", "500", "503", "slow"])
async def test_real_downstream_failure_exhausts_bounded_retries(
    kind: str, fixture_server: str
) -> None:
    engine = create_engine(Settings(database_url=os.environ["DATABASE_URL"]))
    sessions = create_session_factory(engine)
    url = f"{fixture_server}/{kind}/{uuid4().hex}"
    async with sessions() as session:
        repo = SqlAlchemyRepository(session)
        job = await repo.create_job([url])
        await repo.schedule_frontier_urls(job_id=job.id, urls=[url], max_attempts=2)
        await session.commit()
    started = time.monotonic()
    try:
        async with AioHttpFetcher(
            timeout_seconds=0.05,
            user_agent="AtlasFixture",
            max_response_bytes=4096,
            allow_private_networks=True,
        ) as fetcher:
            worker = FrontierWorker.with_session_factory(
                owner="poison-fixture",
                session_factory=sessions,
                fetcher=fetcher,
                batch_size=1,
                lease_seconds=2,
                concurrency=1,
                retry_policy=RetryPolicy(max_retries=1, base_delay_seconds=0, jitter_seconds=0),
            )
            await worker.run_once()
            await worker.run_once()
        async with sessions() as session:
            stats = await SqlAlchemyRepository(session).frontier_stats(job_id=job.id)
            attempts = await session.scalar(
                select(CrawlFrontierItem.attempt_count).where(CrawlFrontierItem.job_id == job.id)
            )
            pages = await session.scalar(
                select(func.count()).select_from(Page).where(Page.normalized_url == url)
            )
        assert stats.dead == 1 and stats.pending == 0 and stats.leased == 0
        assert attempts == 2 and pages == 0
        evidence(
            f"downstream-{kind}",
            {
                "passed": True,
                "attempts": attempts,
                "logical_pages": pages,
                "frontier": asdict(stats),
                "duration_seconds": time.monotonic() - started,
                "max_fetch_attempts": 4,
            },
        )
    finally:
        async with sessions() as session:
            await session.execute(delete(CrawlJob).where(CrawlJob.id == job.id))
            await session.commit()
        await engine.dispose()


async def test_redirect_to_metadata_is_blocked(fixture_server: str) -> None:
    async with AioHttpFetcher(
        timeout_seconds=1,
        user_agent="AtlasFixture",
        max_response_bytes=4096,
        allow_private_networks=True,
    ) as fetcher:
        result = await fetcher.fetch(f"{fixture_server}/redirect/{uuid4().hex}")
    assert result.error_type == "UnsafeUrlError"
    evidence(
        "metadata-redirect",
        {"passed": True, "error_category": result.error_type, "body_bytes": len(result.body)},
    )


async def test_actual_pool_exhaustion_is_bounded_and_recovers() -> None:
    engine = create_engine(
        Settings(
            database_url=os.environ["DATABASE_URL"],
            database_pool_size=1,
            database_max_overflow=0,
            database_pool_timeout=0.05,
        )
    )
    started = time.monotonic()
    try:
        async with engine.connect():
            with pytest.raises(PoolTimeout):
                async with engine.connect():
                    pass
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT 1")) == 1
        evidence(
            "pool-exhaustion",
            {
                "passed": True,
                "pool_size": 1,
                "timeout_seconds": 0.05,
                "recovered": True,
                "duration_seconds": time.monotonic() - started,
            },
        )
    finally:
        await engine.dispose()


async def test_database_connection_interruption_degrades_readiness_and_recovers() -> None:
    original = make_url(os.environ["DATABASE_URL"])
    blocked = False
    writers: set[asyncio.StreamWriter] = set()
    tasks: set[asyncio.Task[object]] = set()

    async def relay(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while data := await reader.read(65536):
                writer.write(data)
                await writer.drain()
        finally:
            writer.close()

    async def proxy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task is not None:
            tasks.add(task)
        if blocked:
            writer.close()
            if task is not None:
                tasks.discard(task)
            return
        backend_reader, backend_writer = await asyncio.open_connection(
            original.host or "localhost", original.port or 5432
        )
        writers.update((writer, backend_writer))
        try:
            await asyncio.gather(relay(reader, backend_writer), relay(backend_reader, writer))
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()
            backend_writer.close()
            writers.difference_update((writer, backend_writer))
            if task is not None:
                tasks.discard(task)

    server = await asyncio.start_server(proxy, "127.0.0.1", 0)
    proxy_port = server.sockets[0].getsockname()[1]
    key = uuid4().hex
    app = create_app(
        settings=Settings(
            database_url=original.set(host="127.0.0.1", port=proxy_port).render_as_string(
                hide_password=False
            ),
            metrics_key=key,
        )
    )
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                assert (await client.get("/ready")).status_code == 200
                blocked = True
                for writer in list(writers):
                    writer.close()
                started = time.monotonic()
                assert (await client.get("/live")).status_code == 200
                assert (await client.get("/ready")).status_code == 503
                failed = await client.get(
                    "/internal/metrics", headers={"Authorization": f"Bearer {key}"}
                )
                assert "atlaspipe_telemetry_database_up 0.0" in failed.text
                blocked = False
                assert (await client.get("/ready")).status_code == 200
                restored = await client.get(
                    "/internal/metrics", headers={"Authorization": f"Bearer {key}"}
                )
                assert "atlaspipe_telemetry_database_up 1.0" in restored.text
                evidence(
                    "database-interruption",
                    {
                        "passed": True,
                        "fault_readiness": 503,
                        "liveness": 200,
                        "restored_readiness": 200,
                        "detection_and_recovery_seconds": time.monotonic() - started,
                        "trigger": "close DB TCP connections and reject reconnections "
                        "in an owned proxy",
                    },
                )
    finally:
        server.close()
        await server.wait_closed()
        for writer in list(writers):
            writer.close()
        for task in list(tasks):
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_graceful_stop_finishes_inflight_job(fixture_server: str) -> None:
    engine = create_engine(Settings(database_url=os.environ["DATABASE_URL"]))
    sessions = create_session_factory(engine)
    url = f"{fixture_server}/slow/{uuid4().hex}"
    async with sessions() as session:
        repo = SqlAlchemyRepository(session)
        job = await repo.create_job([url])
        await repo.schedule_frontier_urls(job_id=job.id, urls=[url])
        await session.commit()
    started_fetch = asyncio.Event()

    class SignalledFetcher(AioHttpFetcher):
        async def fetch(self, url: str):
            started_fetch.set()
            return await super().fetch(url)

    stop = asyncio.Event()
    try:
        async with SignalledFetcher(
            timeout_seconds=1,
            user_agent="AtlasFixture",
            max_response_bytes=4096,
            allow_private_networks=True,
        ) as fetcher:
            worker = FrontierWorker.with_session_factory(
                owner="graceful-fixture",
                session_factory=sessions,
                fetcher=fetcher,
                batch_size=1,
                lease_seconds=2,
                concurrency=1,
            )
            running = asyncio.create_task(
                run_with_shutdown(worker, stop, drain_seconds=1, poll_seconds=0.01)
            )
            await asyncio.wait_for(started_fetch.wait(), 3)
            started = time.monotonic()
            stop.set()
            await asyncio.wait_for(running, 2)
        async with sessions() as session:
            stats = await SqlAlchemyRepository(session).frontier_stats(job_id=job.id)
        assert stats.complete == 1 and stats.leased == 0
        evidence(
            "graceful-drain",
            {
                "passed": True,
                "frontier": asdict(stats),
                "drain_seconds": time.monotonic() - started,
                "trigger": "shared signal stop event; actual POSIX SIGTERM delivery "
                "unverified on Windows",
            },
        )
    finally:
        async with sessions() as session:
            await session.execute(delete(CrawlJob).where(CrawlJob.id == job.id))
            await session.execute(delete(Page).where(Page.normalized_url == url))
            await session.commit()
        await engine.dispose()
