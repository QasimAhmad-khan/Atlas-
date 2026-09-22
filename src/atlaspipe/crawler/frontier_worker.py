from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from atlaspipe.crawler.fetcher import FetchResult
from atlaspipe.db.repositories import FrontierLease, PageRepository
from atlaspipe.parsing.html_parser import HtmlMetadataParser
from atlaspipe.pipeline.pipeline import page_from_fetch_result


class Fetcher(Protocol):
    async def fetch(self, url: str) -> FetchResult: ...


@dataclass(frozen=True)
class FrontierWorkerResult:
    claimed: int = 0
    completed: int = 0
    failed: int = 0


class FrontierWorker:
    def __init__(
        self,
        *,
        owner: str,
        repository: PageRepository,
        fetcher: Fetcher,
        batch_size: int,
        lease_seconds: int,
        concurrency: int,
    ) -> None:
        self._owner = owner
        self._repository = repository
        self._fetcher = fetcher
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds
        self._concurrency = concurrency
        self._parser = HtmlMetadataParser()

    async def run_once(self) -> FrontierWorkerResult:
        leases = await self._repository.acquire_frontier_batch(
            owner=self._owner,
            batch_size=self._batch_size,
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
            failed=sum(1 for outcome in outcomes if not outcome),
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
            )
            if result.claimed == 0:
                empty_polls += 1
                await asyncio.sleep(0)
            else:
                empty_polls = 0
        return total

    async def _process_with_limit(
        self,
        lease: FrontierLease,
        semaphore: asyncio.Semaphore,
    ) -> bool:
        async with semaphore:
            return await self._process(lease)

    async def _process(self, lease: FrontierLease) -> bool:
        result = await self._fetcher.fetch(lease.url)
        if result.error_type is not None:
            await self._repository.fail_frontier_item(
                lease.id,
                error_type=result.error_type,
                error_message=result.error_message or "",
                retry_after_seconds=0,
            )
            return False

        page = page_from_fetch_result(result, parser=self._parser)
        if page is None:
            await self._repository.fail_frontier_item(
                lease.id,
                error_type="UnpersistableResponse",
                error_message=f"response for {lease.url} could not be converted to a page record",
                retry_after_seconds=0,
            )
            return False

        await self._repository.save_pages([page])
        await self._repository.complete_frontier_item(lease.id)
        return True
