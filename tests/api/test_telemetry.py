from __future__ import annotations

from fastapi.testclient import TestClient

from atlaspipe.api.app import create_app
from atlaspipe.config import Settings
from atlaspipe.db.repositories import InMemoryRepository


def test_metrics_require_secret_and_routes_have_bounded_labels() -> None:
    app = create_app(
        repository=InMemoryRepository.empty(), settings=Settings(metrics_key="metrics-key")
    )
    with TestClient(app) as client:
        assert client.get("/internal/metrics").status_code == 401
        response = client.get("/jobs/123456789", headers={"X-Request-ID": "request-1"})
        assert response.headers["X-Request-ID"] == "request-1"
        assert len(response.headers["X-Trace-ID"]) == 32
        metrics = client.get("/internal/metrics", headers={"Authorization": "Bearer metrics-key"})
        assert metrics.status_code == 200
        assert 'route="/jobs/{job_id}"' in metrics.text
        assert "123456789" not in metrics.text


def test_trace_context_is_stored_with_job() -> None:
    repository = InMemoryRepository.empty()
    app = create_app(repository=repository, settings=Settings(api_key="write-key"))
    parent = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
    with TestClient(app) as client:
        response = client.post(
            "/crawl",
            headers={"Authorization": "Bearer write-key", "traceparent": parent},
            json={"urls": ["https://example.com"]},
        )
    assert response.status_code == 202
    stored = repository.traceparents[response.json()["id"]]
    assert stored is not None
    assert stored.split("-")[1] == parent.split("-")[1]
