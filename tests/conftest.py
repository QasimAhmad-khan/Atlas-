from collections.abc import Iterator

import pytest

from atlaspipe.config import get_settings


@pytest.fixture(autouse=True)
def isolate_local_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # A developer's .env must not supply secrets or cloud authentication to fixture tests.
    for key, value in {
        "ENVIRONMENT": "local",
        "SERVICE": "api",
        "DATABASE_AUTH": "password",
        "DB_HOST": "",
        "DATABASE_SSL": "false",
        "ALLOW_PRIVATE_NETWORKS": "false",
        "API_KEY": "",
        "API_READ_KEY": "",
        "METRICS_KEY": "",
        "WORKER_METRICS_PORT": "0",
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()
