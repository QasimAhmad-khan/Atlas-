from __future__ import annotations

from fastapi import APIRouter, Request

from atlaspipe.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    database = "not_configured"
    if getattr(request.app.state, "repository", None) is not None:
        database = "repository_available"
    return HealthResponse(status="healthy", database=database)
