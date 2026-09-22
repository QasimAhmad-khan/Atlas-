from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from atlaspipe.crawler.fetcher import FetchResult
from atlaspipe.db.repositories import InMemoryRepository
from atlaspipe.pipeline.pipeline import CrawlPipeline


class SyntheticFetcher:
    async def fetch(self, url: str) -> FetchResult:
        index = url.rsplit("-", maxsplit=1)[-1]
        html = (
            "<html><head>"
            f"<title>Benchmark {index}</title>"
            f"<meta name='description' content='Benchmark page {index}'>"
            "</head><body><a href='/next'>Next</a></body></html>"
        )
        return FetchResult(
            url=url,
            final_url=url,
            status=200,
            headers={"content-type": "text/html"},
            body=html.encode(),
            response_time_ms=1,
        )


async def run_scale(size: int, concurrency: int) -> dict[str, float | int]:
    repository = InMemoryRepository.empty()
    pipeline = CrawlPipeline(
        fetcher=SyntheticFetcher(),
        repository=repository,
        max_concurrency=concurrency,
        per_domain_concurrency=max(1, min(concurrency, 5)),
        requests_per_second=10_000,
        batch_size=100,
    )
    urls = [f"https://benchmark.example/page-{index}" for index in range(size)]
    started = time.perf_counter()
    result = await pipeline.run(urls)
    elapsed = time.perf_counter() - started
    return {
        "records": size,
        "concurrency": concurrency,
        "elapsed_seconds": round(elapsed, 6),
        "records_per_second": round(result.saved / elapsed, 2) if elapsed else 0,
        "saved": result.saved,
        "failed": result.failed,
        "duplicates": result.duplicates,
    }


async def main_async() -> list[dict[str, float | int]]:
    results = []
    for size in [100, 1_000]:
        for concurrency in [1, 5, 10]:
            results.append(await run_scale(size, concurrency))
    return results


def main() -> None:
    results = asyncio.run(main_async())
    output = Path("benchmarks/results/ingestion_benchmark.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
