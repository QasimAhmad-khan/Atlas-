from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from atlaspipe.crawler.fetcher import FetchResult
from atlaspipe.crawler.rate_limiter import DomainConcurrencyLimiter, TokenBucketRateLimiter
from atlaspipe.crawler.retry import RetryPolicy, retry_after_seconds, should_retry_status
from atlaspipe.db.repositories import FrontierLease, PageRepository, SqlAlchemyRepository
from atlaspipe.parsing.html_parser import HtmlMetadataParser
from atlaspipe.pipeline.pipeline import page_from_fetch_result


class Fetcher(Protocol):
    async def fetch(self, url: str) -> FetchResult: ...


@dataclass(frozen=True)
class FrontierWorkerResult:
    claimed: int = 0
    completed: int = 0
    failed: int = 0
    stale_rejected: int = 0


RepositoryContextFactory = Callable[[], AbstractAsyncContextManager[PageRepository]]


class FrontierWorker:
    def __init__(
        self,
        *,
        owner: str,
        repository: PageRepository | None = None,
        repository_context_factory: RepositoryContextFactory | None = None,
        fetcher: Fetcher,
        batch_size: int,
        lease_seconds: int,
        concurrency: int,
        per_domain_concurrency: int = 100,
        requests_per_second: float = 1_000,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        if (repository is None) == (repository_context_factory is None):
            raise ValueError("provide exactly one of repository or repository_context_factory")
        self._owner = owner
        self._repository = repository
        self._repository_context_factory = repository_context_factory
        self._fetcher = fetcher
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds
        self._concurrency = concurrency
        self._rate_limiter = TokenBucketRateLimiter(requests_per_second)
        self._domain_limiter = DomainConcurrencyLimiter(per_domain_concurrency)
        self._retry_policy = retry_policy or RetryPolicy(max_retries=0)
        self._parser = HtmlMetadataParser()

    @classmethod
    def with_session_factory(
        cls,
        *,
        owner: str,
        session_factory: async_sessionmaker[AsyncSession],
        fetcher: Fetcher,
        batch_size: int,
        lease_seconds: int,
        concurrency: int,
        per_domain_concurrency: int = 100,
        requests_per_second: float = 1_000,
        retry_policy: RetryPolicy | None = None,
    ) -> FrontierWorker:
        return cls(
            owner=owner,
            repository_context_factory=lambda: _sqlalchemy_repository_context(session_factory),
            fetcher=fetcher,
            batch_size=batch_size,
            lease_seconds=lease_seconds,
            concurrency=concurrency,
            per_domain_concurrency=per_domain_concurrency,
            requests_per_second=requests_per_second,
            retry_policy=retry_policy,
        )

    async def run_once(self) -> FrontierWorkerResult:
        claim_size = min(self._batch_size, self._concurrency)
        async with self._repository_context() as repository:
            leases = await repository.acquire_frontier_batch(
                owner=self._owner,
                batch_size=claim_size,
                lease_seconds=self._lease_seconds,
            )
        if not leases:
            return FrontierWorkerResult()

        semaphore = asyncio.Semaphore(self._concurrency)
        outcomes = await asyncio.gather(
            *(self._process_with_limit(lease, semaphore) for lease in leases)
        )
        return FrontierWorkerResult(
            claimed=len(leases),
            completed=sum(1 for outcome in outcomes if outcome),
            failed=sum(1 for outcome in outcomes if outcome is False),
            stale_rejected=sum(1 for outcome in outcomes if outcome is None),
        )

    async def run_until_drained(self, *, max_empty_polls: int = 3) -> FrontierWorkerResult:
        empty_polls = 0
        total = FrontierWorkerResult()
        while empty_polls < max_empty_polls:
            result = await self.run_once()
            total = FrontierWorkerResult(
                claimed=total.claimed + result.claimed,
                completed=total.completed + result.completed,
                failed=total.failed + result.failed,
                stale_rejected=total.stale_rejected + result.stale_rejected,
            )
            if result.claimed == 0:
                empty_polls += 1
                await asyncio.sleep(0)
            else:
                empty_polls = 0
        return total

    async def run_continuously(
        self,
        *,
        stop_event: asyncio.Event,
        poll_interval_seconds: float = 1.0,
    ) -> FrontierWorkerResult:
        total = FrontierWorkerResult()
        while not stop_event.is_set():
            result = await self.run_once()
            total = FrontierWorkerResult(
                claimed=total.claimed + result.claimed,
                completed=total.completed + result.completed,
                failed=total.failed + result.failed,
                stale_rejected=total.stale_rejected + result.stale_rejected,
            )
            if result.claimed == 0:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=poll_interval_seconds)
                except TimeoutError:
                    pass
        return total

    async def _process_with_limit(
        self,
        lease: FrontierLease,
        semaphore: asyncio.Semaphore,
    ) -> bool | None:
        async with semaphore:
            return await self._process(lease)

    async def _process(self, lease: FrontierLease) -> bool | None:
        result = await self._fetch_with_retries(lease.url)
        if result.error_type is not None:
            async with self._repository_context() as repository:
                accepted = await repository.fail_frontier_item(
                    lease.id,
                    lease_owner=lease.lease_owner,
                    lease_token=lease.lease_token,
                    error_type=result.error_type,
                    error_message=result.error_message or "",
                    retry_after_seconds=math.ceil(self._retry_delay_for_result(result, 0)),
                )
            return False if accepted else None

        if should_retry_status(result.status):
            async with self._repository_context() as repository:
                accepted = await repository.fail_frontier_item(
                    lease.id,
                    lease_owner=lease.lease_owner,
                    lease_token=lease.lease_token,
                    error_type="TransientHttpStatus",
                    error_message=f"HTTP {result.status}",
                    retry_after_seconds=math.ceil(
                        self._retry_delay_for_result(
                            result,
                            self._retry_policy.max_retries + 1,
                        )
                    ),
                )
            return False if accepted else None

        page = page_from_fetch_result(result, parser=self._parser)
        if page is None:
            async with self._repository_context() as repository:
                message = f"response for {lease.url} could not be converted to a page record"
                accepted = await repository.fail_frontier_item(
                    lease.id,
                    lease_owner=lease.lease_owner,
                    lease_token=lease.lease_token,
                    error_type="UnpersistableResponse",
                    error_message=message,
                    retry_after_seconds=0,
                )
            return False if accepted else None

        async with self._repository_context() as repository:
            accepted = await repository.save_page_and_complete_frontier_item(
                item_id=lease.id,
                lease_owner=lease.lease_owner,
                lease_token=lease.lease_token,
                page=page,
            )
        return True if accepted else None

    async def _fetch_with_retries(self, url: str) -> FetchResult:
        result: FetchResult | None = None
        for attempt in range(1, self._retry_policy.max_retries + 2):
            domain = urlsplit(url).hostname or ""
            await self._rate_limiter.acquire()
            async with self._domain_limiter.limit(domain):
                result = await self._fetcher.fetch(url)
            if result.error_type is None and not should_retry_status(result.status):
                return result
            if attempt <= self._retry_policy.max_retries:
                await asyncio.sleep(self._retry_delay_for_result(result, attempt))
        if result is None:
            raise RuntimeError("fetch retry loop produced no result")
        return result

    def _retry_delay_for_result(self, result: FetchResult, attempt: int) -> float:
        header_delay = retry_after_seconds(result.headers.get("retry-after"))
        if header_delay is not None:
            return float(header_delay)
        return self._retry_policy.delay_for_attempt(attempt)

    @asynccontextmanager
    async def _repository_context(self) -> AsyncIterator[PageRepository]:
        if self._repository is not None:
            yield self._repository
            return
        if self._repository_context_factory is None:
            raise RuntimeError("repository context factory is not configured")
        async with self._repository_context_factory() as repository:
            yield repository


@asynccontextmanager
async def _sqlalchemy_repository_context(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[PageRepository]:
    async with session_factory() as session:
        try:
            yield SqlAlchemyRepository(session)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
