"""Deterministic synthetic rows for an isolated API benchmark database."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url

from atlaspipe.config import get_settings
from atlaspipe.db.repositories import SqlAlchemyRepository
from atlaspipe.db.session import create_engine, create_session_factory
from atlaspipe.schemas.page import PageRecord


async def seed(rows: int, output: Path) -> None:
    settings = get_settings()
    if not (make_url(settings.database_url).database or "").startswith("atlaspipe_perf"):
        raise ValueError(
            "use a dedicated atlaspipe_perf database; never seed a live crawl database"
        )
    engine = create_engine(settings)
    sessions = create_session_factory(engine)
    started = time.perf_counter()
    try:
        async with sessions() as session:
            for start in range(0, rows, 500):
                pages = [
                    PageRecord(
                        url=f"https://d{i % 100}.benchmark.invalid/page/{i}",
                        normalized_url=f"https://d{i % 100}.benchmark.invalid/page/{i}",
                        domain=f"d{i % 100}.benchmark.invalid",
                        title=f"Fixture {i}",
                        http_status=200 if i % 10 else 404,
                        content_length=1024,
                    )
                    for i in range(start, min(start + 500, rows))
                ]
                await SqlAlchemyRepository(session).save_pages(pages)
            await session.commit()
            observed = await session.scalar(text("SELECT count(*) FROM pages"))
            version = await session.scalar(text("SELECT version()"))
        if observed != rows:
            raise RuntimeError(
                "benchmark fixture row count differs; use a fresh dedicated database"
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(
            output.write_text,
            json.dumps(
                {
                    "environment": "local synthetic fixture",
                    "rows": observed,
                    "database_version": version,
                    "seed_seconds": time.perf_counter() - started,
                    "external_fetches": 0,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=10000)
    parser.add_argument("--output", type=Path, default=Path("artifacts/performance/seed.json"))
    args = parser.parse_args()
    if not 1 <= args.rows <= 1000000:
        parser.error("rows must be between 1 and 1,000,000")
    asyncio.run(seed(args.rows, args.output))
