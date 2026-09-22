from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from aiohttp import web
from sqlalchemy import func, select

from atlaspipe.config import get_settings
from atlaspipe.db.models import CrawlFrontierItem, Page
from atlaspipe.db.repositories import SqlAlchemyRepository
from atlaspipe.db.session import create_engine, create_session_factory


@dataclass
class WorkerProcess:
    owner: str
    process: subprocess.Popen[bytes]
    log_file: object


async def run_demo(
    *,
    records: int,
    worker_processes: int,
    kill_worker_index: int,
    worker_concurrency: int,
    batch_size: int,
    lease_seconds: int,
    slow_records: int,
    slow_delay_seconds: float,
    kill_after_seconds: float,
    timeout_seconds: float,
    output: Path,
) -> dict[str, object]:
    settings = get_settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    run_id = uuid4().hex
    started = time.perf_counter()

    app = web.Application()
    app.router.add_get("/run/{run_id}/page/{index}", _fixture_page)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    sockets = site._server.sockets if site._server is not None else []
    if not sockets:
        raise RuntimeError("fixture server did not bind a socket")
    port = int(sockets[0].getsockname()[1])
    base_url = f"http://127.0.0.1:{port}/run/{run_id}"

    urls = [
        f"{base_url}/page/{index}?delay={slow_delay_seconds if index < slow_records else 0}"
        for index in range(records)
    ]
    processes: list[WorkerProcess] = []

    try:
        async with session_factory() as session:
            repository = SqlAlchemyRepository(session)
            job = await repository.create_job(urls)
            scheduled = await repository.schedule_frontier_urls(job_id=job.id, urls=urls)
            await session.commit()

        processes = _start_workers(
            run_id=run_id,
            worker_processes=worker_processes,
            worker_concurrency=worker_concurrency,
            batch_size=batch_size,
            lease_seconds=lease_seconds,
            request_timeout_seconds=max(10, int(slow_delay_seconds + 5)),
            output=output,
        )

        killed = processes[kill_worker_index]
        orphaned_ids = await _wait_for_worker_leases(
            session_factory=session_factory,
            job_id=job.id,
            owner=killed.owner,
            timeout_seconds=kill_after_seconds,
        )
        if not orphaned_ids:
            await asyncio.sleep(kill_after_seconds)
            orphaned_ids = await _leased_ids_for_owner(session_factory, job.id, killed.owner)

        killed.process.kill()
        await asyncio.to_thread(killed.process.wait, 10)
        killed.log_file.close()

        final_stats = await _wait_for_accounting(
            session_factory=session_factory,
            job_id=job.id,
            scheduled=scheduled,
            timeout_seconds=timeout_seconds,
        )
        _stop_workers(
            [worker for index, worker in enumerate(processes) if index != kill_worker_index]
        )
        processes = []

        recovered = await _recovered_count(session_factory, orphaned_ids)
        logical_pages = await _logical_page_count(session_factory, base_url)
        elapsed_seconds = time.perf_counter() - started
        result = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "run_id": run_id,
            "failure_mode": "real worker process killed while owning PostgreSQL leases",
            "scheduled": scheduled,
            "completed": final_stats["complete"],
            "dead": final_stats["dead"],
            "pending": final_stats["pending"],
            "leased": final_stats["leased"],
            "worker_processes": worker_processes,
            "workers_killed": 1,
            "killed_worker": killed.owner,
            "leases_orphaned": len(orphaned_ids),
            "leases_recovered": recovered,
            "stale_completions_rejected": 0,
            "logical_pages": logical_pages,
            "logical_duplicates": max(0, final_stats["complete"] - logical_pages),
            "lost": scheduled - final_stats["complete"] - final_stats["dead"],
            "lease_seconds": lease_seconds,
            "worker_concurrency": worker_concurrency,
            "batch_size": batch_size,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "throughput_pages_per_second": round(final_stats["complete"] / elapsed_seconds, 2)
            if elapsed_seconds > 0
            else 0,
            "notes": [
                "Leases are not manually expired in this experiment.",
                (
                    "The killed worker cannot attempt a stale completion; stale fencing "
                    "is covered by postgres_frontier_recovery_demo.json."
                ),
            ],
        }
        await asyncio.to_thread(_write_json, output, result)
        return result
    finally:
        _stop_workers(processes)
        await runner.cleanup()
        await engine.dispose()


async def _fixture_page(request: web.Request) -> web.Response:
    delay = float(request.query.get("delay", "0"))
    if delay > 0:
        await asyncio.sleep(delay)
    url = str(request.url)
    html = f"""
    <html>
      <head>
        <title>{url}</title>
        <meta name="description" content="worker death fixture">
      </head>
      <body><main>{url}</main></body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")


def _start_workers(
    *,
    run_id: str,
    worker_processes: int,
    worker_concurrency: int,
    batch_size: int,
    lease_seconds: int,
    request_timeout_seconds: int,
    output: Path,
) -> list[WorkerProcess]:
    project_root = Path(__file__).resolve().parents[1]
    log_dir = output.parent / "worker_death_logs" / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    workers: list[WorkerProcess] = []
    for index in range(worker_processes):
        owner = f"worker-death-{run_id}-{index}"
        env = os.environ.copy()
        env.update(
            {
                "PYTHONPATH": str(project_root / "src"),
                "ATLASPIPE_WORKER_ID": owner,
                "ALLOW_PRIVATE_NETWORKS": "true",
                "FRONTIER_LEASE_SECONDS": str(lease_seconds),
                "FRONTIER_POLL_INTERVAL_SECONDS": "0.1",
                "MAX_CONCURRENCY": str(worker_concurrency),
                "PER_DOMAIN_CONCURRENCY": str(worker_concurrency * worker_processes),
                "REQUESTS_PER_SECOND": str(max(1000, worker_concurrency * worker_processes * 20)),
                "REQUEST_TIMEOUT": str(request_timeout_seconds),
                "MAX_RETRIES": "0",
                "BATCH_SIZE": str(batch_size),
            }
        )
        log_file = (log_dir / f"{owner}.log").open("wb")
        process = subprocess.Popen(
            [sys.executable, "-m", "atlaspipe.worker"],
            cwd=project_root,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        workers.append(WorkerProcess(owner=owner, process=process, log_file=log_file))
    return workers


def _stop_workers(workers: list[WorkerProcess]) -> None:
    for worker in workers:
        if worker.process.poll() is None:
            worker.process.terminate()
    for worker in workers:
        try:
            worker.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            worker.process.kill()
            worker.process.wait(timeout=10)
        worker.log_file.close()


def _write_json(output: Path, result: dict[str, object]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")


async def _wait_for_worker_leases(
    *,
    session_factory: object,
    job_id: int,
    owner: str,
    timeout_seconds: float,
) -> list[int]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        ids = await _leased_ids_for_owner(session_factory, job_id, owner)
        if ids:
            return ids
        await asyncio.sleep(0.1)
    return []


async def _leased_ids_for_owner(
    session_factory: object,
    job_id: int,
    owner: str,
) -> list[int]:
    async with session_factory() as session:
        rows = (
            await session.scalars(
                select(CrawlFrontierItem.id).where(
                    CrawlFrontierItem.job_id == job_id,
                    CrawlFrontierItem.state == "leased",
                    CrawlFrontierItem.lease_owner == owner,
                )
            )
        ).all()
    return [int(row) for row in rows]


async def _wait_for_accounting(
    *,
    session_factory: object,
    job_id: int,
    scheduled: int,
    timeout_seconds: float,
) -> dict[str, int]:
    deadline = time.monotonic() + timeout_seconds
    last_stats = {"pending": 0, "leased": 0, "complete": 0, "dead": 0}
    while time.monotonic() < deadline:
        async with session_factory() as session:
            repository = SqlAlchemyRepository(session)
            stats = await repository.frontier_stats(job_id=job_id)
        last_stats = stats.__dict__
        if stats.complete + stats.dead >= scheduled:
            return last_stats
        await asyncio.sleep(0.5)
    return last_stats


async def _recovered_count(session_factory: object, orphaned_ids: list[int]) -> int:
    if not orphaned_ids:
        return 0
    async with session_factory() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(CrawlFrontierItem)
                .where(
                    CrawlFrontierItem.id.in_(orphaned_ids),
                    CrawlFrontierItem.attempt_count > 1,
                    CrawlFrontierItem.state.in_(["complete", "dead"]),
                )
            )
            or 0
        )


async def _logical_page_count(session_factory: object, base_url: str) -> int:
    async with session_factory() as session:
        return int(
            await session.scalar(
                select(func.count()).select_from(Page).where(Page.url.like(f"{base_url}%"))
            )
            or 0
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Kill a real PostgreSQL-backed worker process.")
    parser.add_argument("--records", type=int, default=100_000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--kill-worker-index", type=int, default=1)
    parser.add_argument("--worker-concurrency", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--lease-seconds", type=int, default=5)
    parser.add_argument("--slow-records", type=int, default=80)
    parser.add_argument("--slow-delay-seconds", type=float, default=8)
    parser.add_argument("--kill-after-seconds", type=float, default=5)
    parser.add_argument("--timeout-seconds", type=float, default=600)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/results/postgres_worker_death_demo.json"),
    )
    args = parser.parse_args()

    result = asyncio.run(
        run_demo(
            records=args.records,
            worker_processes=args.workers,
            kill_worker_index=args.kill_worker_index,
            worker_concurrency=args.worker_concurrency,
            batch_size=args.batch_size,
            lease_seconds=args.lease_seconds,
            slow_records=args.slow_records,
            slow_delay_seconds=args.slow_delay_seconds,
            kill_after_seconds=args.kill_after_seconds,
            timeout_seconds=args.timeout_seconds,
            output=args.output,
        )
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
