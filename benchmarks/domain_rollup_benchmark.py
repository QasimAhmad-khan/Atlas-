from __future__ import annotations

import asyncio
import json
import statistics
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from atlaspipe.config import get_settings
from atlaspipe.db.models import DomainStat, Page
from atlaspipe.db.repositories import SqlAlchemyRepository
from atlaspipe.db.session import create_engine, create_session_factory


async def timed(repetitions: int, action: Callable[[], Awaitable[None]]) -> list[float]:
    timings: list[float] = []
    for _ in range(repetitions):
        started = time.perf_counter()
        await action()
        timings.append((time.perf_counter() - started) * 1000)
    return timings


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "avg_ms": statistics.fmean(values),
        "min_ms": min(values),
        "max_ms": max(values),
    }


async def run_benchmark() -> dict[str, object]:
    settings = get_settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    async with session_factory() as session:
        repository = SqlAlchemyRepository(session)

        async def baseline_aggregate() -> None:
            await session.execute(
                select(Page.domain, func.count())
                .group_by(Page.domain)
                .order_by(func.count().desc())
            )

        baseline = await timed(5, baseline_aggregate)
        refresh_started = time.perf_counter()
        refreshed_domains = await repository.refresh_domain_stats()
        await session.commit()
        refresh_ms = (time.perf_counter() - refresh_started) * 1000

        async def rollup_lookup() -> None:
            await session.execute(
                select(DomainStat.domain, DomainStat.page_count).order_by(
                    DomainStat.page_count.desc(),
                    DomainStat.domain,
                )
            )

        rollup = await timed(5, rollup_lookup)
        pages = int(await session.scalar(select(func.count()).select_from(Page)) or 0)
        domains = int(await session.scalar(select(func.count()).select_from(DomainStat)) or 0)

    await engine.dispose()

    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "pages": pages,
        "domains": domains,
        "refreshed_domains": refreshed_domains,
        "refresh_ms": refresh_ms,
        "baseline_aggregate": summarize(baseline),
        "rollup_lookup": summarize(rollup),
    }


def main() -> None:
    result = asyncio.run(run_benchmark())
    output = Path("benchmarks/results/domain_rollup_benchmark.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
