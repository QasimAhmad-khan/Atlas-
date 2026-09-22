from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class CrawlRequest(BaseModel):
    urls: list[HttpUrl] = Field(min_length=1, max_length=500)


class CrawlJobResponse(BaseModel):
    id: int
    status: str
    requested_urls: list[str]
    processed_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
