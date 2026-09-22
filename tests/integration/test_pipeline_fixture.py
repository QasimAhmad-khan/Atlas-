from __future__ import annotations

from atlaspipe.crawler.fetcher import FetchResult
from atlaspipe.db.repositories import InMemoryRepository
from atlaspipe.pipeline.pipeline import CrawlPipeline


class FixtureFetcher:
    async def fetch(self, url: str) -> FetchResult:
        html = """
        <html>
          <head><title>Fixture</title><meta name="description" content="Fixture page"></head>
          <body><a href="/next">Next</a></body>
        </html>
        """
        return FetchResult(
            url=url,
            final_url=url,
            status=200,
            headers={"content-type": "text/html"},
            body=html.encode(),
            response_time_ms=12,
        )


async def test_pipeline_processes_fixture_url_end_to_end() -> None:
    repository = InMemoryRepository.empty()
    pipeline = CrawlPipeline(
        fetcher=FixtureFetcher(),
        repository=repository,
        max_concurrency=2,
        per_domain_concurrency=1,
        requests_per_second=100,
        batch_size=2,
    )

    result = await pipeline.run(["https://example.com"])

    assert result.requested == 1
    assert result.processed == 1
    assert result.saved == 1
    assert result.failed == 0
    pages, total = await repository.list_pages(limit=10, offset=0)
    assert total == 1
    assert pages[0].title == "Fixture"
    assert pages[0].internal_link_count == 1
