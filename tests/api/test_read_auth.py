from fastapi.testclient import TestClient

from atlaspipe.api.app import create_app
from atlaspipe.config import Settings
from atlaspipe.db.repositories import InMemoryRepository


def test_data_reads_require_credentials_but_health_stays_available() -> None:
    app = create_app(
        repository=InMemoryRepository.empty(),
        settings=Settings(api_key="write-key", api_read_key="read-key"),
    )
    with TestClient(app) as client:
        for path in ("/pages", "/stats", "/jobs/1"):
            assert client.get(path).status_code == 401
        assert client.get("/pages", headers={"Authorization": "Bearer read-key"}).status_code == 200
        assert (
            client.get("/stats", headers={"Authorization": "Bearer write-key"}).status_code == 200
        )
        assert client.get("/live").status_code == 200
        assert client.get("/ready").status_code == 200
