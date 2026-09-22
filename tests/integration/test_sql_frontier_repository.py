from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from atlaspipe.config import Settings
from atlaspipe.db.models import CrawlFrontierItem, Page
from atlaspipe.db.repositories import SqlAlchemyRepository
from atlaspipe.db.session import create_engine, create_session_factory
from atlaspipe.schemas.page import PageRecord

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL is required for PostgreSQL integration tests",
)


async def test_sql_frontier_recovers_expired_lease_and_rejects_stale_page_write() -> None:
    settings = Settings(database_url=os.environ["DATABASE_URL"])
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    run_id = uuid4().hex
    url = f"https://sql-frontier-{run_id}.test/page"
    normalized_url = url

    async with session_factory() as session:
        repository = SqlAlchemyRepository(session)
        job = await repository.create_job([url])
        await repository.schedule_frontier_urls(job_id=job.id, urls=[url])
        stale = (
            await repository.acquire_frontier_batch(
                owner="worker-1",
                batch_size=1,
                lease_seconds=30,
            )
        )[0]
        await session.commit()

    async with session_factory() as session:
        await session.execute(
            update(CrawlFrontierItem)
            .where(CrawlFrontierItem.id == stale.id)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()

    async with session_factory() as session:
        repository = SqlAlchemyRepository(session)
        recovered = (
            await repository.acquire_frontier_batch(
                owner="worker-2",
                batch_size=1,
                lease_seconds=30,
            )
        )[0]
        accepted = await repository.save_page_and_complete_frontier_item(
            item_id=stale.id,
            lease_owner=stale.lease_owner,
            lease_token=stale.lease_token,
            page=PageRecord(
                url=url,
                normalized_url=normalized_url,
                domain=f"sql-frontier-{run_id}.test",
                http_status=200,
            ),
        )
        await session.commit()

    async with session_factory() as session:
        page_count = int(
            await session.scalar(
                select(func.count()).select_from(Page).where(Page.normalized_url == normalized_url)
            )
            or 0
        )
        repository = SqlAlchemyRepository(session)
        completed = await repository.save_page_and_complete_frontier_item(
            item_id=recovered.id,
            lease_owner=recovered.lease_owner,
            lease_token=recovered.lease_token,
            page=PageRecord(
                url=url,
                normalized_url=normalized_url,
                domain=f"sql-frontier-{run_id}.test",
                http_status=200,
            ),
        )
        await session.commit()

    await engine.dispose()

    assert accepted is False
    assert page_count == 0
    assert recovered.attempt_count == 2
    assert completed is True
