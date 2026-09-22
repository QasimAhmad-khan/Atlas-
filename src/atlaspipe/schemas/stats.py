from __future__ import annotations

from pydantic import BaseModel


class StatsResponse(BaseModel):
    jobs: int
    pages: int
    successful_pages: int
    failed_attempts: int


class DomainStats(BaseModel):
    domain: str
    pages: int


class StatusCodeStats(BaseModel):
    status_code: int
    pages: int
