from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from atlaspipe.crawler.fetcher import FetchResult
from atlaspipe.crawler.rate_limiter import DomainConcurrencyLimiter, TokenBucketRateLimiter
from atlaspipe.db.repositories import PageRepository
from atlaspipe.parsing.html_parser import HtmlMetadataParser
from atlaspipe.pipeline.deduplication import Deduplicator, sha256_hexdigest
from atlaspipe.pipeline.normalization import normalize_text_metadata, normalize_url
from atlaspipe.pipeline.validation import validate_public_url
from atlaspipe.schemas.page import PageRecord


class Fetcher(Protocol):
    async def fetch(self, url: str) -> FetchResult: ...


@dataclass(frozen=True)
class PipelineResult:
    requested: int
    processed: int
    saved: int
    failed: int
    duplicates: int


class CrawlPipeline:
    def __init__(
        self,
        *,
        fetcher: Fetcher,
        repository: PageRepository,
        max_concurrency: int,
        per_domain_concurrency: int,
        requests_per_second: int,
        batch_size: int,
        queue_size: int | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._repository = repository
        self._max_concurrency = max_concurrency
        self._batch_size = batch_size
        self._queue_size = queue_size or max(max_concurrency * 2, 1)
        self._global_limiter = TokenBucketRateLimiter(requests_per_second)
        self._domain_limiter = DomainConcurrencyLimiter(per_domain_concurrency)
        self._parser = HtmlMetadataParser()
        self._deduplicator = Deduplicator()

    async def run(self, urls: list[str]) -> PipelineResult:
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=self._queue_size)
        output: asyncio.Queue[PageRecord | None] = asyncio.Queue(maxsize=self._queue_size)
        counters = {"processed": 0, "failed": 0, "duplicates": 0}

        writer = asyncio.create_task(self._writer(output))
        workers = [
            asyncio.create_task(self._worker(queue, output, counters))
            for _ in range(self._max_concurrency)
        ]

        for url in urls:
            await queue.put(str(url))
        for _ in workers:
            await queue.put(None)

        await queue.join()
        await output.put(None)
        saved = await writer
        await asyncio.gather(*workers)

        return PipelineResult(
            requested=len(urls),
            processed=counters["processed"],
            saved=saved,
            failed=counters["failed"],
            duplicates=counters["duplicates"],
        )

    async def _worker(
        self,
        queue: asyncio.Queue[str | None],
        output: asyncio.Queue[PageRecord | None],
        counters: dict[str, int],
    ) -> None:
        while True:
            url = await queue.get()
            try:
                if url is None:
                    return
                validation = validate_public_url(url)
                if not validation.is_valid:
                    counters["failed"] += 1
                    continue
                domain = urlsplit(url).hostname or ""
                await self._global_limiter.acquire()
                async with self._domain_limiter.limit(domain):
                    result = await self._fetcher.fetch(url)
                page = self._result_to_page(result)
                if page is None:
                    counters["failed"] += 1
                    continue
                dedupe = self._deduplicator.check_and_remember(
                    normalized_url=page.normalized_url,
                    content_hash=page.content_hash or "",
                    text=page.description or page.title or "",
                )
                if dedupe.normalized_url_seen or dedupe.content_hash_seen:
                    counters["duplicates"] += 1
                    continue
                counters["processed"] += 1
                await output.put(page)
            finally:
                queue.task_done()

    async def _writer(self, output: asyncio.Queue[PageRecord | None]) -> int:
        batch: list[PageRecord] = []
        saved = 0
        while True:
            item = await output.get()
            try:
                if item is None:
                    if batch:
                        saved += await self._repository.save_pages(batch)
                    return saved
                batch.append(item)
                if len(batch) >= self._batch_size:
                    saved += await self._repository.save_pages(batch)
                    batch.clear()
            finally:
                output.task_done()

    def _result_to_page(self, result: FetchResult) -> PageRecord | None:
        if result.error_type is not None or result.status is None:
            return None
        content_type = result.content_type or ""
        if "html" not in content_type.lower() and result.body:
            return None

        html = result.body.decode("utf-8", errors="replace")
        parsed = self._parser.parse(url=result.final_url, html=html, headers=result.headers)
        normalized = normalize_url(result.final_url)
        domain = urlsplit(normalized).hostname or ""

        return PageRecord(
            url=result.url,
            normalized_url=normalized,
            canonical_url=parsed.canonical_url,
            domain=domain,
            title=normalize_text_metadata(parsed.title),
            description=normalize_text_metadata(parsed.description),
            http_status=result.status,
            content_type=content_type or None,
            content_length=len(result.body),
            html_hash=sha256_hexdigest(result.body),
            content_hash=sha256_hexdigest(parsed.text),
            internal_link_count=parsed.internal_link_count,
            external_link_count=parsed.external_link_count,
            outbound_link_count=parsed.outbound_link_count,
            response_time_ms=result.response_time_ms,
        )
