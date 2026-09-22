from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from statistics import mean
from typing import Any

import asyncpg  # type: ignore[import-untyped]

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://atlaspipe:atlaspipe@localhost:55432/atlaspipe",
).replace("+asyncpg", "")

PAGE_COLUMNS = [
    "url",
    "normalized_url",
    "canonical_url",
    "domain",
    "title",
    "description",
    "http_status",
    "content_type",
    "content_length",
    "html_hash",
    "content_hash",
    "internal_link_count",
    "external_link_count",
    "outbound_link_count",
    "response_time_ms",
]


def make_rows(run_id: str, scale: int, size: int, start: int) -> list[tuple[Any, ...]]:
    domain = f"hv-{run_id}-{scale}.example"
    return [
        (
            f"https://{domain}/page-{index}",
            f"https://{domain}/page-{index}",
            None,
            domain,
            f"High volume page {index}",
            f"High volume PostgreSQL COPY stress row {index}",
            200 if index % 20 else 500,
            "text/html",
            1024 + (index % 8192),
            f"{index:064x}"[-64:],
            f"{(index * 104729):064x}"[-64:],
            index % 11,
            index % 13,
            (index % 11) + (index % 13),
            index % 750,
        )
        for index in range(start, start + size)
    ]


async def copy_scale(
    connection: asyncpg.Connection,
    *,
    run_id: str,
    scale: int,
    chunk_size: int,
) -> dict[str, float | int | str]:
    started = time.perf_counter()
    copied = 0
    for offset in range(0, scale, chunk_size):
        size = min(chunk_size, scale - offset)
        rows = make_rows(run_id, scale, size, offset)
        await connection.copy_records_to_table(
            "pages",
            records=rows,
            columns=PAGE_COLUMNS,
        )
        copied += size
    elapsed = time.perf_counter() - started
    return {
        "mode": "copy_records_to_table",
        "records": copied,
        "chunk_size": chunk_size,
        "elapsed_seconds": round(elapsed, 6),
        "records_per_second": round(copied / elapsed, 2),
    }


async def time_query(
    connection: asyncpg.Connection,
    sql: str,
    *args: object,
    repeats: int = 7,
) -> dict[str, float]:
    timings: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        await connection.fetch(sql, *args)
        timings.append((time.perf_counter() - started) * 1000)
    return {
        "avg_ms": round(mean(timings), 3),
        "min_ms": round(min(timings), 3),
        "max_ms": round(max(timings), 3),
    }


async def explain(connection: asyncpg.Connection, sql: str, *args: object) -> list[str]:
    rows = await connection.fetch(f"EXPLAIN ANALYZE {sql}", *args)
    return [row["QUERY PLAN"] for row in rows]


async def run() -> dict[str, Any]:
    run_id = uuid.uuid4().hex[:10]
    connection = await asyncpg.connect(DATABASE_URL)
    try:
        await connection.execute("SET application_name = 'atlaspipe_high_volume_benchmark'")
        copy_results = []
        for scale in [100_000, 500_000, 1_000_000]:
            copy_results.append(
                await copy_scale(
                    connection,
                    run_id=run_id,
                    scale=scale,
                    chunk_size=50_000,
                )
            )

        await connection.execute("ANALYZE pages")

        domain = f"hv-{run_id}-1000000.example"
        lookup_url = f"https://{domain}/page-750000"
        query_results = {
            "lookup_by_normalized_url": await time_query(
                connection,
                "SELECT id, title FROM pages WHERE normalized_url = $1",
                lookup_url,
            ),
            "filter_by_domain_recent": await time_query(
                connection,
                "SELECT id FROM pages WHERE domain = $1 ORDER BY created_at DESC LIMIT 100",
                domain,
            ),
            "recent_pages": await time_query(
                connection,
                "SELECT id FROM pages ORDER BY created_at DESC LIMIT 100",
            ),
            "status_code_filter": await time_query(
                connection,
                "SELECT id FROM pages WHERE http_status = $1 LIMIT 100",
                200,
            ),
            "domain_aggregate": await time_query(
                connection,
                "SELECT domain, count(*) FROM pages GROUP BY domain "
                "ORDER BY count(*) DESC LIMIT 10",
            ),
        }
        explain_results = {
            "lookup_by_normalized_url": await explain(
                connection,
                "SELECT id, title FROM pages WHERE normalized_url = $1",
                lookup_url,
            ),
            "filter_by_domain_recent": await explain(
                connection,
                "SELECT id FROM pages WHERE domain = $1 ORDER BY created_at DESC LIMIT 100",
                domain,
            ),
            "domain_aggregate": await explain(
                connection,
                "SELECT domain, count(*) FROM pages GROUP BY domain "
                "ORDER BY count(*) DESC LIMIT 10",
            ),
        }
        total_pages = await connection.fetchval("SELECT count(*) FROM pages")
        database_size = await connection.fetchval(
            "SELECT pg_size_pretty(pg_database_size(current_database()))"
        )
        return {
            "database_url": DATABASE_URL,
            "run_id": run_id,
            "total_pages_after_run": total_pages,
            "database_size_after_run": database_size,
            "copy_results": copy_results,
            "query_results": query_results,
            "explain_analyze": explain_results,
        }
    finally:
        await connection.close()


def main() -> None:
    result = asyncio.run(run())
    output = Path("benchmarks/results/postgres_high_volume_benchmark.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
