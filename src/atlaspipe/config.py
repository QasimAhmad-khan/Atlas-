from __future__ import annotations

from functools import lru_cache

from pydantic import Field, PositiveInt, SecretStr, model_validator
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
    api_key: SecretStr = SecretStr("")
    api_read_key: SecretStr = SecretStr("")
    metrics_key: SecretStr = SecretStr("")
    api_requests_per_minute: PositiveInt = 30
    api_urls_per_minute: PositiveInt = 1000
    api_max_body_bytes: PositiveInt = 65536
    database_pool_size: PositiveInt = 10
    database_max_overflow: int = Field(default=5, ge=0)
    database_pool_timeout: float = Field(default=5, gt=0)
    database_command_timeout: float = Field(default=10, gt=0)
    worker_drain_seconds: float = Field(default=30, gt=0)
    worker_heartbeat_seconds: float = Field(default=5, gt=0)
    worker_stale_seconds: float = Field(default=30, gt=0)
    environment: str = "local"
    release: str = "development"

    @model_validator(mode="after")
    def production_safety(self) -> Settings:
        if self.environment == "production":
            if len(self.api_key.get_secret_value()) < 32:
                raise ValueError("production API_KEY must contain at least 32 characters")
            if len(self.metrics_key.get_secret_value()) < 32:
                raise ValueError("production METRICS_KEY must contain at least 32 characters")
            if self.allow_private_networks:
                raise ValueError("private crawling is forbidden in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
