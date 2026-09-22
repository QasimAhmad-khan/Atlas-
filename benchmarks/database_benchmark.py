from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from atlaspipe.db.repositories import InMemoryRepository
from atlaspipe.schemas.page import PageRecord


def make_pages(size: int) -> list[PageRecord]:
    return [
        PageRecord(
            url=f"https://db-benchmark.example/page-{index}",
            normalized_url=f"https://db-benchmark.example/page-{index}",
            domain="db-benchmark.example",
            title=f"DB Benchmark {index}",
            http_status=200,
        )
        for index in range(size)
    ]


async def run_insert_mode(size: int, batch_size: int) -> dict[str, float | int | str]:
    repository = InMemoryRepository.empty()
    pages = make_pages(size)
    started = time.perf_counter()
    saved = 0
    for offset in range(0, size, batch_size):
        saved += await repository.save_pages(pages[offset : offset + batch_size])
    insert_elapsed = time.perf_counter() - started

    query_started = time.perf_counter()
    listed, total = await repository.list_pages(limit=50, offset=0, domain="db-benchmark.example")
    query_elapsed = time.perf_counter() - query_started

    return {
        "mode": "single_row" if batch_size == 1 else "batch",
        "records": size,
        "batch_size": batch_size,
        "saved": saved,
        "insert_elapsed_seconds": round(insert_elapsed, 6),
        "records_per_second": round(saved / insert_elapsed, 2) if insert_elapsed else 0,
        "query_elapsed_ms": round(query_elapsed * 1000, 3),
        "query_returned": len(listed),
        "query_total": total,
    }


async def main_async() -> list[dict[str, float | int | str]]:
    results = []
    for size in [100, 1_000, 10_000]:
        results.append(await run_insert_mode(size, 1))
        results.append(await run_insert_mode(size, 100))
    return results


def main() -> None:
    results = asyncio.run(main_async())
    output = Path("benchmarks/results/database_benchmark.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
