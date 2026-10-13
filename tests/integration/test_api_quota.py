from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete

from atlaspipe.api.app import create_app
from atlaspipe.config import Settings
from atlaspipe.db.models import CrawlJob

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL required")


async def test_two_api_replicas_enforce_one_atomic_quota() -> None:
    key = uuid4().hex
    settings = Settings(
        database_url=os.environ["DATABASE_URL"], api_key=key, api_requests_per_minute=3
    )
    first, second = create_app(settings=settings), create_app(settings=settings)
    async with first.router.lifespan_context(first), second.router.lifespan_context(second):
        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=first), base_url="http://test"
            ) as a,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=second), base_url="http://test"
            ) as b,
        ):
            responses = await asyncio.gather(
                *[
                    (a if i % 2 else b).post(
                        "/crawl",
                        headers={"Authorization": f"Bearer {key}"},
                        json={"urls": [f"https://quota-{key}.test/{i}"]},
                    )
                    for i in range(12)
                ]
            )
            async with first.state.engine.begin() as connection:
                await connection.execute(
                    delete(CrawlJob).where(
                        CrawlJob.id.in_([r.json()["id"] for r in responses if r.status_code == 202])
                    )
                )
    assert sum(r.status_code == 202 for r in responses) == 3
    assert sum(r.status_code == 429 for r in responses) == 9
