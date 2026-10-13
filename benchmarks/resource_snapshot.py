"""Snapshot actual PostgreSQL counters and authenticated API metrics during a local run."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import text

from atlaspipe.db.session import create_engine


async def snapshot() -> None:
    engine = create_engine()
    try:
        async with engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT xact_commit, xact_rollback, blks_read, blks_hit, "
                            "tup_returned, tup_fetched FROM pg_stat_database "
                            "WHERE datname=current_database()"
                        )
                    )
                )
                .mappings()
                .one()
            )
            result = {"timestamp": datetime.now(UTC).isoformat(), "database": dict(row)}
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "http://127.0.0.1:58000/internal/metrics",
                headers={"Authorization": f"Bearer {os.environ['METRICS_KEY']}"},
            )
            response.raise_for_status()
        await asyncio.to_thread(
            Path(os.environ["SNAPSHOT_OUTPUT"]).write_text,
            json.dumps(result, indent=2),
            encoding="utf-8",
        )
        await asyncio.to_thread(
            Path(os.environ["SNAPSHOT_OUTPUT"] + ".prom").write_text,
            response.text,
            encoding="utf-8",
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(snapshot())
