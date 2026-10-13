from __future__ import annotations

import os
from uuid import uuid4

import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import delete

from atlaspipe.api.app import create_app
from atlaspipe.config import Settings
from atlaspipe.crawler.fetcher import FetchResult
from atlaspipe.crawler.frontier_worker import FrontierWorker
from atlaspipe.db.models import CrawlJob, Page
from atlaspipe.db.repositories import SqlAlchemyRepository
from atlaspipe.db.session import create_engine, create_session_factory

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL required")


class Fixture:
    async def fetch(self, url: str) -> FetchResult:
        return FetchResult(
            url, url, 200, {"content-type": "text/html"}, b"<title>trace fixture</title>", 1
        )


async def test_postgres_queue_preserves_api_to_worker_trace() -> None:
    settings = Settings(database_url=os.environ["DATABASE_URL"], api_key=uuid4().hex)
    app = create_app(settings=settings)
    exporter = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    url = f"https://trace-{uuid4().hex}.test/page"
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/crawl",
                headers={"Authorization": f"Bearer {settings.api_key.get_secret_value()}"},
                json={"urls": [url]},
            )
        assert response.status_code == 202
    engine = create_engine(settings)
    sessions = create_session_factory(engine)
    worker = FrontierWorker.with_session_factory(
        owner="trace-worker",
        session_factory=sessions,
        fetcher=Fixture(),
        batch_size=1,
        lease_seconds=30,
        concurrency=1,
    )
    result = await worker.run_once()
    assert result.completed == 1
    spans = [
        s
        for s in exporter.get_finished_spans()
        if s.name in {"http.request", "crawl.process", "crawl.persist"}
    ]
    assert {s.name for s in spans} == {"http.request", "crawl.process", "crawl.persist"}
    assert len({s.context.trace_id for s in spans if s.context}) == 1
    job_trace = spans[0].context
    assert job_trace is not None
    database_spans = [
        s
        for s in exporter.get_finished_spans()
        if s.name == "db.query" and s.context and s.context.trace_id == job_trace.trace_id
    ]
    assert database_spans
    assert all("db.statement" not in s.attributes for s in database_spans if s.attributes)
    async with sessions() as session:
        leases = await SqlAlchemyRepository(session).frontier_stats(job_id=response.json()["id"])
        assert leases.complete == 1
        await session.execute(delete(CrawlJob).where(CrawlJob.id == response.json()["id"]))
        await session.execute(delete(Page).where(Page.normalized_url == url))
        await session.commit()
    await engine.dispose()
    exporter.shutdown()
