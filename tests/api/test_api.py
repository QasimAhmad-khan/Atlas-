from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from atlaspipe.api.app import create_app
from atlaspipe.db.repositories import InMemoryRepository
from atlaspipe.schemas.page import PageRecord


def test_health_and_crawl_job_endpoints() -> None:
    repository = InMemoryRepository.empty()
    app = create_app(repository=repository)
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "healthy"

        created = client.post("/crawl", json={"urls": ["https://example.com"]})
        assert created.status_code == 202
        job = created.json()
        assert job["id"] == 1
        assert job["requested_urls"] == ["https://example.com/"]
        assert len(app.state.repository.frontier) == 1

        fetched = client.get("/jobs/1")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == 1


def test_pages_filtering_pagination_and_stats() -> None:
    repository = InMemoryRepository.empty()
    app = create_app(repository=repository)
    now = datetime.now(UTC)
    repository.pages[1] = PageRecord(
        id=1,
        url="https://example.com",
        normalized_url="https://example.com/",
        domain="example.com",
        http_status=200,
        created_at=now,
    )
    repository.pages[2] = PageRecord(
        id=2,
        url="https://other.test",
        normalized_url="https://other.test/",
        domain="other.test",
        http_status=404,
        created_at=now,
    )
    with TestClient(app) as client:
        pages = client.get("/pages", params={"domain": "example.com", "limit": 1})
        assert pages.status_code == 200
        assert pages.json()["total"] == 1
        assert pages.json()["items"][0]["domain"] == "example.com"

        page = client.get("/pages/1")
        assert page.status_code == 200
        assert page.json()["normalized_url"] == "https://example.com/"

        domain = client.get("/domains/example.com")
        assert domain.status_code == 200
        assert len(domain.json()) == 1

        stats = client.get("/stats")
        assert stats.status_code == 200
        assert stats.json()["pages"] == 2

        status_codes = client.get("/stats/status-codes")
        assert status_codes.status_code == 200
        assert {row["status_code"] for row in status_codes.json()} == {200, 404}
