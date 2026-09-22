from __future__ import annotations

from datetime import UTC, datetime, timedelta

from atlaspipe.crawler.fetcher import FetchResult
from atlaspipe.crawler.frontier_worker import FrontierWorker
from atlaspipe.db.repositories import InMemoryRepository


class StableFetcher:
    async def fetch(self, url: str) -> FetchResult:
        html = f"""
        <html>
          <head><title>{url}</title></head>
          <body><main>{url}</main></body>
        </html>
        """
        return FetchResult(
            url=url,
            final_url=url,
            status=200,
            headers={"content-type": "text/html"},
            body=html.encode(),
            response_time_ms=5,
        )


class FailingFetcher:
    async def fetch(self, url: str) -> FetchResult:
        return FetchResult(
            url=url,
            final_url=url,
            status=None,
            headers={},
            body=b"",
            response_time_ms=5,
            error_type="FixtureFailure",
            error_message="forced failure",
        )


async def test_frontier_schedules_unique_urls_per_job() -> None:
    repository = InMemoryRepository.empty()
    job = await repository.create_job(["https://example.com/a", "https://example.com/a"])

    scheduled = await repository.schedule_frontier_urls(
        job_id=job.id,
        urls=["https://example.com/a", "https://example.com/a"],
    )

    stats = await repository.frontier_stats(job_id=job.id)
    assert scheduled == 1
    assert stats.pending == 1


async def test_frontier_recovers_expired_leases() -> None:
    repository = InMemoryRepository.empty()
    job = await repository.create_job(["https://example.com/a"])
    await repository.schedule_frontier_urls(job_id=job.id, urls=job.requested_urls)

    first = await repository.acquire_frontier_batch(
        owner="worker-1",
        batch_size=10,
        lease_seconds=30,
    )
    assert len(first) == 1
    second = await repository.acquire_frontier_batch(
        owner="worker-2",
        batch_size=10,
        lease_seconds=30,
    )
    assert second == []

    repository.frontier[first[0].id]["lease_expires_at"] = datetime.now(UTC) - timedelta(seconds=1)
    recovered = await repository.acquire_frontier_batch(
        owner="worker-2",
        batch_size=10,
        lease_seconds=30,
    )

    assert len(recovered) == 1
    assert recovered[0].lease_owner == "worker-2"
    assert recovered[0].attempt_count == 2


async def test_frontier_rejects_stale_lease_completion() -> None:
    repository = InMemoryRepository.empty()
    job = await repository.create_job(["https://example.com/a"])
    await repository.schedule_frontier_urls(job_id=job.id, urls=job.requested_urls)

    stale = (
        await repository.acquire_frontier_batch(
            owner="worker-1",
            batch_size=1,
            lease_seconds=30,
        )
    )[0]
    repository.frontier[stale.id]["lease_expires_at"] = datetime.now(UTC) - timedelta(seconds=1)
    recovered = (
        await repository.acquire_frontier_batch(
            owner="worker-2",
            batch_size=1,
            lease_seconds=30,
        )
    )[0]

    stale_completion = await repository.complete_frontier_item(
        stale.id,
        lease_owner=stale.lease_owner,
        lease_token=stale.lease_token,
    )
    valid_completion = await repository.complete_frontier_item(
        recovered.id,
        lease_owner=recovered.lease_owner,
        lease_token=recovered.lease_token,
    )

    stats = await repository.frontier_stats(job_id=job.id)
    assert stale_completion is False
    assert valid_completion is True
    assert stats.complete == 1


async def test_frontier_worker_persists_pages_and_marks_work_complete() -> None:
    repository = InMemoryRepository.empty()
    job = await repository.create_job(["https://example.com/a", "https://example.com/b"])
    await repository.schedule_frontier_urls(job_id=job.id, urls=job.requested_urls)
    worker = FrontierWorker(
        owner="worker-1",
        repository=repository,
        fetcher=StableFetcher(),
        batch_size=10,
        lease_seconds=30,
        concurrency=2,
    )

    result = await worker.run_until_drained()

    pages, total_pages = await repository.list_pages(limit=10, offset=0)
    stats = await repository.frontier_stats(job_id=job.id)
    assert result.claimed == 2
    assert result.completed == 2
    assert result.failed == 0
    assert total_pages == 2
    assert {page.normalized_url for page in pages} == {
        "https://example.com/a",
        "https://example.com/b",
    }
    assert stats.complete == 2


async def test_duplicate_delivery_still_produces_one_logical_page() -> None:
    repository = InMemoryRepository.empty()
    job = await repository.create_job(["https://example.com/a"])
    await repository.schedule_frontier_urls(job_id=job.id, urls=job.requested_urls)
    worker = FrontierWorker(
        owner="worker-1",
        repository=repository,
        fetcher=StableFetcher(),
        batch_size=10,
        lease_seconds=30,
        concurrency=1,
    )

    await worker.run_once()
    await repository.schedule_frontier_urls(job_id=job.id + 1, urls=job.requested_urls)
    duplicate_worker = FrontierWorker(
        owner="worker-2",
        repository=repository,
        fetcher=StableFetcher(),
        batch_size=10,
        lease_seconds=30,
        concurrency=1,
    )
    await duplicate_worker.run_once()

    pages, total_pages = await repository.list_pages(limit=10, offset=0)
    assert total_pages == 1
    assert pages[0].normalized_url == "https://example.com/a"


async def test_frontier_worker_retries_then_dead_letters_failures() -> None:
    repository = InMemoryRepository.empty()
    job = await repository.create_job(["https://example.com/fail"])
    await repository.schedule_frontier_urls(
        job_id=job.id,
        urls=job.requested_urls,
        max_attempts=2,
    )
    worker = FrontierWorker(
        owner="worker-1",
        repository=repository,
        fetcher=FailingFetcher(),
        batch_size=10,
        lease_seconds=30,
        concurrency=1,
    )

    first = await worker.run_once()
    second = await worker.run_once()

    stats = await repository.frontier_stats(job_id=job.id)
    assert first.failed == 1
    assert second.failed == 1
    assert stats.dead == 1
