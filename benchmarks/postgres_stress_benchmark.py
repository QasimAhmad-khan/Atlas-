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


def make_rows(run_id: str, size: int) -> list[tuple[Any, ...]]:
    domain = f"stress-{run_id}.example"
    return [
        (
            f"https://{domain}/page-{index}",
            f"https://{domain}/page-{index}",
            None,
            domain,
            f"Stress page {index}",
            f"Synthetic PostgreSQL stress row {index}",
            200 if index % 10 else 404,
            "text/html",
            512 + index,
            f"{index:064x}"[-64:],
            f"{(index * 17):064x}"[-64:],
            index % 5,
            index % 7,
            (index % 5) + (index % 7),
            index % 250,
        )
        for index in range(size)
    ]


INSERT_SQL = """
INSERT INTO pages (
    url,
    normalized_url,
    canonical_url,
    domain,
    title,
    description,
    http_status,
    content_type,
    content_length,
    html_hash,
    content_hash,
    internal_link_count,
    external_link_count,
    outbound_link_count,
    response_time_ms
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15
)
ON CONFLICT (normalized_url) DO NOTHING
"""


async def time_query(
    pool: asyncpg.Pool, sql: str, *args: object, repeats: int = 5
) -> dict[str, float]:
    timings: list[float] = []
    async with pool.acquire() as connection:
        for _ in range(repeats):
            started = time.perf_counter()
            await connection.fetch(sql, *args)
            timings.append((time.perf_counter() - started) * 1000)
    return {
        "avg_ms": round(mean(timings), 3),
        "min_ms": round(min(timings), 3),
        "max_ms": round(max(timings), 3),
    }


async def explain(pool: asyncpg.Pool, sql: str, *args: object) -> list[str]:
    async with pool.acquire() as connection:
        rows = await connection.fetch(f"EXPLAIN ANALYZE {sql}", *args)
    return [row["QUERY PLAN"] for row in rows]


async def insert_single_row(pool: asyncpg.Pool, rows: list[tuple[Any, ...]]) -> float:
    started = time.perf_counter()
    async with pool.acquire() as connection:
        async with connection.transaction():
            for row in rows:
                await connection.execute(INSERT_SQL, *row)
    return time.perf_counter() - started


async def insert_batches(
    pool: asyncpg.Pool,
    rows: list[tuple[Any, ...]],
    batch_size: int,
) -> float:
    started = time.perf_counter()
    async with pool.acquire() as connection:
        async with connection.transaction():
            for offset in range(0, len(rows), batch_size):
                await connection.executemany(INSERT_SQL, rows[offset : offset + batch_size])
    return time.perf_counter() - started


async def run() -> dict[str, Any]:
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    try:
        run_id = uuid.uuid4().hex[:10]
        insert_results = []
        for size in [1_000, 10_000, 50_000]:
            single_rows = make_rows(f"{run_id}-single-{size}", size)
            single_elapsed = await insert_single_row(pool, single_rows)
            insert_results.append(
                {
                    "mode": "single_row",
                    "records": size,
                    "elapsed_seconds": round(single_elapsed, 6),
                    "records_per_second": round(size / single_elapsed, 2),
                }
            )

            batch_rows = make_rows(f"{run_id}-batch-{size}", size)
            batch_elapsed = await insert_batches(pool, batch_rows, batch_size=500)
            insert_results.append(
                {
                    "mode": "batch_executemany",
                    "records": size,
                    "batch_size": 500,
                    "elapsed_seconds": round(batch_elapsed, 6),
                    "records_per_second": round(size / batch_elapsed, 2),
                }
            )

        domain = f"stress-{run_id}-batch-50000.example"
        lookup_url = f"https://{domain}/page-25000"
        query_results = {
            "lookup_by_normalized_url": await time_query(
                pool,
                "SELECT id, title FROM pages WHERE normalized_url = $1",
                lookup_url,
            ),
            "filter_by_domain": await time_query(
                pool,
                "SELECT id FROM pages WHERE domain = $1 ORDER BY created_at DESC LIMIT 100",
                domain,
            ),
            "recent_pages": await time_query(
                pool,
                "SELECT id FROM pages ORDER BY created_at DESC LIMIT 100",
            ),
            "status_code_filter": await time_query(
                pool,
                "SELECT id FROM pages WHERE http_status = $1 LIMIT 100",
                200,
            ),
            "domain_aggregate": await time_query(
                pool,
                "SELECT domain, count(*) FROM pages GROUP BY domain "
                "ORDER BY count(*) DESC LIMIT 10",
            ),
        }
        explain_results = {
            "lookup_by_normalized_url": await explain(
                pool,
                "SELECT id, title FROM pages WHERE normalized_url = $1",
                lookup_url,
            ),
            "filter_by_domain": await explain(
                pool,
                "SELECT id FROM pages WHERE domain = $1 ORDER BY created_at DESC LIMIT 100",
                domain,
            ),
        }

        async with pool.acquire() as connection:
            total_pages = await connection.fetchval("SELECT count(*) FROM pages")

        return {
            "database_url": DATABASE_URL,
            "run_id": run_id,
            "total_pages_after_run": total_pages,
            "insert_results": insert_results,
            "query_results": query_results,
            "explain_analyze": explain_results,
        }
    finally:
        await pool.close()


def main() -> None:
    result = asyncio.run(run())
    output = Path("benchmarks/results/postgres_stress_benchmark.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
