"""Controlled fixture process for persistence-boundary crash tests."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from atlaspipe.config import get_settings
from atlaspipe.crawler.fetcher import AioHttpFetcher, FetchResult
from atlaspipe.crawler.frontier_worker import FrontierWorker
from atlaspipe.db.repositories import PageRepository, SqlAlchemyRepository
from atlaspipe.db.session import create_engine, create_session_factory
from atlaspipe.schemas.page import PageRecord


async def child(point: str, marker: Path) -> None:
    engine = create_engine(get_settings())
    sessions = create_session_factory(engine)

    async def pause() -> None:
        await asyncio.to_thread(marker.write_text, point, encoding="utf-8")
        await asyncio.Event().wait()

    class FixtureFetcher(AioHttpFetcher):
        async def fetch(self, url: str) -> FetchResult:
            if urlsplit(url).hostname != "127.0.0.1":
                raise ValueError("fault worker only fetches its local fixture")
            result = await super().fetch(url)
            if point == "after_fetch":
                await pause()
            return result

    class PausedRepository(SqlAlchemyRepository):
        async def save_pages(self, pages: list[PageRecord]) -> int:
            saved = await super().save_pages(pages)
            if point == "after_persist":
                await pause()
            return saved

    @asynccontextmanager
    async def repository_context() -> AsyncIterator[PageRepository]:
        async with sessions() as session:
            try:
                yield PausedRepository(session)
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    try:
        async with FixtureFetcher(
            timeout_seconds=2,
            user_agent="AtlasFixture",
            max_response_bytes=4096,
            allow_private_networks=True,
        ) as fetcher:
            worker = FrontierWorker(
                owner="boundary-fixture",
                repository_context_factory=repository_context,
                fetcher=fetcher,
                batch_size=1,
                lease_seconds=2,
                concurrency=1,
            )
            await worker.run_once()
            if point == "after_commit":
                await pause()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--point", choices=["after_fetch", "after_persist", "after_commit"], required=True
    )
    parser.add_argument("--marker", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(child(args.point, args.marker))
