from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PageRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    url: str
    normalized_url: str
    canonical_url: str | None = None
    domain: str
    title: str | None = None
    description: str | None = None
    http_status: int | None = None
    content_type: str | None = None
    content_length: int | None = None
    html_hash: str | None = None
    content_hash: str | None = None
    internal_link_count: int = 0
    external_link_count: int = 0
    outbound_link_count: int = 0
    response_time_ms: int | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PageListResponse(BaseModel):
    items: list[PageRecord]
    limit: int
    offset: int
    total: int
