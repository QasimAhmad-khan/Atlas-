from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from atlaspipe.api.app import create_app
from atlaspipe.config import Settings
from atlaspipe.db.repositories import InMemoryRepository


@pytest.mark.parametrize(
    ("header", "expected"), [(None, 401), ("Bearer wrong", 401), ("Bearer read-key", 403)]
)
def test_unauthorized_submission_never_creates_work(header: str | None, expected: int) -> None:
    repository = InMemoryRepository.empty()
    app = create_app(
        repository=repository, settings=Settings(api_key="write-key", api_read_key="read-key")
    )
    with TestClient(app) as client:
        headers = {"Authorization": header} if header else {}
        assert (
            client.post(
                "/crawl", headers=headers, json={"urls": ["https://example.com"]}
            ).status_code
            == expected
        )
        assert client.get("/live").status_code == 200
        assert client.get("/ready").status_code == 200
    assert not repository.jobs
    assert not repository.frontier


def test_quota_and_body_and_url_limits() -> None:
    repository = InMemoryRepository.empty()
    app = create_app(
        repository=repository,
        settings=Settings(
            api_key="write-key",
            api_requests_per_minute=1,
            api_max_body_bytes=128,
        ),
    )
    with TestClient(app, headers={"Authorization": "Bearer write-key"}) as client:
        assert client.post("/crawl", json={"urls": ["https://example.com"]}).status_code == 202
        rejected = client.post("/crawl", json={"urls": ["https://example.com/a"]})
        assert rejected.status_code == 429
        assert rejected.headers["Retry-After"] == "60"
        assert client.post("/crawl", content=b"x" * 129).status_code == 413
        assert (
            client.post("/crawl", json={"urls": ["http://user:secret@example.com"]}).status_code
            == 422
        )
    assert len(repository.jobs) == 1
    assert len(repository.frontier) == 1


def test_unconfigured_key_fails_closed() -> None:
    repository = InMemoryRepository.empty()
    with TestClient(create_app(repository=repository, settings=Settings(api_key=""))) as client:
        assert client.post("/crawl", json={"urls": ["https://example.com"]}).status_code == 503
    assert not repository.jobs


def test_production_configuration_rejects_unsafe_defaults() -> None:
    with pytest.raises(ValueError, match="API_KEY"):
        Settings(environment="production")
    with pytest.raises(ValueError, match="private crawling"):
        Settings(
            environment="production",
            api_key="w" * 32,
            metrics_key="m" * 32,
            allow_private_networks=True,
        )


def test_too_many_urls_never_creates_work() -> None:
    repository = InMemoryRepository.empty()
    app = create_app(repository=repository, settings=Settings(api_key="write-key"))
    with TestClient(app, headers={"Authorization": "Bearer write-key"}) as client:
        assert (
            client.post("/crawl", json={"urls": ["https://example.com"] * 501}).status_code == 422
        )
    assert not repository.jobs
    assert not repository.frontier
