from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from atlaspipe.api.app import create_app
from atlaspipe.config import Settings
from atlaspipe.db.repositories import InMemoryRepository
from atlaspipe.schemas.crawl import CrawlJobResponse


def test_exception_details_are_not_sent_or_logged(caplog: pytest.LogCaptureFixture) -> None:
    class FailingRepository(InMemoryRepository):
        async def create_job(
            self, urls: list[str], *, traceparent: str | None = None
        ) -> CrawlJobResponse:
            raise RuntimeError("fixture-secret-must-not-leak")

    repository = FailingRepository.empty()
    app = create_app(repository=repository, settings=Settings(api_key="write-key"))
    with TestClient(app, headers={"Authorization": "Bearer write-key"}) as client:
        response = client.post("/crawl", json={"urls": ["https://example.com"]})
    assert response.status_code == 500
    assert "fixture-secret-must-not-leak" not in response.text
    assert "fixture-secret-must-not-leak" not in caplog.text
    assert not repository.jobs
