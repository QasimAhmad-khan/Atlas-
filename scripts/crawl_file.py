from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from atlaspipe.config import get_settings
from atlaspipe.crawler.fetcher import AioHttpFetcher
from atlaspipe.db.repositories import InMemoryRepository
from atlaspipe.pipeline.pipeline import CrawlPipeline


async def crawl_urls(urls: list[str]) -> None:
    settings = get_settings()
    repository = InMemoryRepository.empty()
    async with AioHttpFetcher(
        timeout_seconds=settings.request_timeout,
        user_agent=settings.user_agent,
        max_response_bytes=settings.max_response_bytes,
    ) as fetcher:
        pipeline = CrawlPipeline(
            fetcher=fetcher,
            repository=repository,
            max_concurrency=settings.max_concurrency,
            per_domain_concurrency=settings.per_domain_concurrency,
            requests_per_second=settings.requests_per_second,
            batch_size=settings.batch_size,
        )
        result = await pipeline.run(urls)
    print(result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl URLs from a newline-delimited file.")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    urls = [
        line.strip() for line in args.path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    asyncio.run(crawl_urls(urls))


if __name__ == "__main__":
    main()
