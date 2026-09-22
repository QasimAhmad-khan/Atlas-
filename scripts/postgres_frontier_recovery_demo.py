from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from atlaspipe.config import get_settings
from atlaspipe.crawler.fetcher import FetchResult
from atlaspipe.crawler.frontier_worker import FrontierWorker, FrontierWorkerResult
from atlaspipe.db.models import CrawlFrontierItem, Page
from atlaspipe.db.repositories import FrontierLease, SqlAlchemyRepository
from atlaspipe.db.session import create_engine, create_session_factory
from atlaspipe.pipeline.normalization import normalize_url


class DemoFetcher:
    async def fetch(self, url: str) -> FetchResult:
        html = f"""
        <html>
          <head>
            <title>{url}</title>
            <meta name="description" content="postgres frontier recovery fixture">
          </head>
          <body><main>{url}</main></body>
        </html>
        """
        return FetchResult(
            url=url,
            final_url=url,
            status=200,
            headers={"content-type": "text/html"},
            body=html.encode(),
            response_time_ms=3,
        )


async def run_demo(
    *,
    records: int,
    crashed_leases: int,
    worker_count: int,
    batch_size: int,
    lease_seconds: int,
) -> dict[str, object]:
    settings = get_settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    run_id = uuid4().hex
    urls = [f"https://pg-frontier-{run_id}.test/page/{index}" for index in range(records)]

    async with session_factory() as session:
        repository = SqlAlchemyRepository(session)
        job = await repository.create_job(urls)
        scheduled = await repository.schedule_frontier_urls(job_id=job.id, urls=urls)
        abandoned = await repository.acquire_frontier_batch(
            owner="worker-crashed",
            batch_size=crashed_leases,
            lease_seconds=lease_seconds,
        )
        await session.commit()

    abandoned_ids = [lease.id for lease in abandoned]
    stale_lease = abandoned[0] if abandoned else None
    async with session_factory() as session:
        await session.execute(
            update(CrawlFrontierItem)
            .where(CrawlFrontierItem.id.in_(abandoned_ids))
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()

    workers = [
        FrontierWorker.with_session_factory(
            owner=f"worker-{index}",
            session_factory=session_factory,
            fetcher=DemoFetcher(),
            batch_size=batch_size,
            lease_seconds=lease_seconds,
            concurrency=25,
        )
        for index in range(worker_count)
    ]
    results = await asyncio.gather(*(worker.run_until_drained() for worker in workers))

    stale_rejected = 0
    if stale_lease is not None:
        stale_rejected = await _attempt_stale_completion(session_factory, stale_lease)

    async with session_factory() as session:
        repository = SqlAlchemyRepository(session)
        stats = await repository.frontier_stats(job_id=job.id)
        recovered = int(
            await session.scalar(
                select(func.count())
                .select_from(CrawlFrontierItem)
                .where(
                    CrawlFrontierItem.job_id == job.id,
                    CrawlFrontierItem.attempt_count > 1,
                    CrawlFrontierItem.state == "complete",
                )
            )
            or 0
        )
        logical_pages = int(
            await session.scalar(
                select(func.count())
                .select_from(Page)
                .where(Page.normalized_url.in_([normalize_url(url) for url in urls]))
            )
            or 0
        )

    await engine.dispose()

    combined = _combine(results)
    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "records": records,
        "scheduled": scheduled,
        "workers": worker_count,
        "abandoned_leases": len(abandoned),
        "expired_leases_recovered": recovered,
        "worker_results": combined.__dict__,
        "frontier": stats.__dict__,
        "logical_pages": logical_pages,
        "lost_records": scheduled - stats.accounted_for,
        "stale_completions_rejected": stale_rejected,
        "storage_semantics": (
            "PostgreSQL frontier, at-least-once delivery, fenced leases, idempotent page writes"
        ),
    }


async def _attempt_stale_completion(
    session_factory: async_sessionmaker[AsyncSession],
    stale_lease: FrontierLease,
) -> int:
    async with session_factory() as session:
        repository = SqlAlchemyRepository(session)
        accepted = await repository.complete_frontier_item(
            stale_lease.id,
            lease_owner=stale_lease.lease_owner,
            lease_token=stale_lease.lease_token,
        )
        await session.commit()
    return 0 if accepted else 1


def _combine(results: list[FrontierWorkerResult]) -> FrontierWorkerResult:
    return FrontierWorkerResult(
        claimed=sum(result.claimed for result in results),
        completed=sum(result.completed for result in results),
        failed=sum(result.failed for result in results),
        stale_rejected=sum(result.stale_rejected for result in results),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a PostgreSQL frontier recovery demo.")
    parser.add_argument("--records", type=int, default=10_000)
    parser.add_argument("--crashed-leases", type=int, default=500)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--lease-seconds", type=int, default=60)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/results/postgres_frontier_recovery_demo.json"),
    )
    args = parser.parse_args()

    result = asyncio.run(
        run_demo(
            records=args.records,
            crashed_leases=args.crashed_leases,
            worker_count=args.workers,
            batch_size=args.batch_size,
            lease_seconds=args.lease_seconds,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
