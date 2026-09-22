from __future__ import annotations

from functools import lru_cache

from pydantic import Field, PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://atlaspipe:atlaspipe@localhost:5432/atlaspipe"
    test_database_url: str = (
        "postgresql+asyncpg://atlaspipe:atlaspipe@localhost:5432/atlaspipe_test"
    )

    max_concurrency: PositiveInt = 10
    per_domain_concurrency: PositiveInt = 2
    requests_per_second: PositiveInt = 5
    request_timeout: PositiveInt = 10
    max_retries: int = Field(default=3, ge=0)
    batch_size: PositiveInt = 100
    frontier_lease_seconds: PositiveInt = 60
    frontier_poll_interval_seconds: float = Field(default=1.0, gt=0)
    allow_private_networks: bool = False
    max_response_bytes: PositiveInt = 1_048_576
    user_agent: str = "AtlasPipe/0.1 (+https://example.invalid/atlaspipe)"
    log_level: str = "INFO"

    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)


@lru_cache
def get_settings() -> Settings:
    return Settings()
