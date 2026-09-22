from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from atlaspipe.crawler.fetcher import FetchResult
from atlaspipe.crawler.frontier_worker import FrontierWorker
from atlaspipe.db.repositories import InMemoryRepository


class DemoFetcher:
    async def fetch(self, url: str) -> FetchResult:
        html = f"""
        <html>
          <head>
            <title>{url}</title>
            <meta name="description" content="frontier recovery fixture">
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


async def run_demo(*, records: int, batch_size: int, concurrency: int) -> dict[str, object]:
    repository = InMemoryRepository.empty()
    urls = [f"https://fixture-{index % 25}.test/page/{index}" for index in range(records)]
    job = await repository.create_job(urls)
    scheduled = await repository.schedule_frontier_urls(job_id=job.id, urls=urls)

    crashed_leases = await repository.acquire_frontier_batch(
        owner="worker-crashed",
        batch_size=batch_size,
        lease_seconds=300,
    )
    for lease in crashed_leases:
        repository.frontier[lease.id]["lease_expires_at"] = datetime.now(UTC) - timedelta(seconds=1)

    worker = FrontierWorker(
        owner="worker-recovery",
        repository=repository,
        fetcher=DemoFetcher(),
        batch_size=batch_size,
        lease_seconds=60,
        concurrency=concurrency,
    )
    recovered_result = await worker.run_until_drained()

    duplicate_job = await repository.create_job(urls[: min(records, batch_size)])
    duplicate_scheduled = await repository.schedule_frontier_urls(
        job_id=duplicate_job.id,
        urls=duplicate_job.requested_urls,
    )
    duplicate_result = await worker.run_until_drained()

    stats = await repository.frontier_stats(job_id=job.id)
    duplicate_stats = await repository.frontier_stats(job_id=duplicate_job.id)
    _pages, logical_pages = await repository.list_pages(limit=1, offset=0)

    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "records": records,
        "scheduled": scheduled,
        "initially_leased_by_crashed_worker": len(crashed_leases),
        "recovered_worker": recovered_result.__dict__,
        "duplicate_delivery": {
            "scheduled": duplicate_scheduled,
            "worker": duplicate_result.__dict__,
            "logical_pages_after_duplicate_delivery": logical_pages,
        },
        "frontier": stats.__dict__,
        "duplicate_frontier": duplicate_stats.__dict__,
        "logical_pages": logical_pages,
        "lost_records": scheduled - stats.accounted_for,
        "delivery_semantics": "at-least-once frontier delivery, idempotent page storage",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a deterministic frontier recovery demo.")
    parser.add_argument("--records", type=int, default=10_000)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/results/frontier_recovery_demo.json"),
    )
    args = parser.parse_args()

    result = asyncio.run(
        run_demo(
            records=args.records,
            batch_size=args.batch_size,
            concurrency=args.concurrency,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
