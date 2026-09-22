from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import text

from atlaspipe.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    if getattr(request.app.state, "repository", None) is not None:
        return HealthResponse(status="healthy", database="in_memory_repository")

    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        return HealthResponse(status="unhealthy", database="not_configured")

    try:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        return HealthResponse(status="unhealthy", database=f"unreachable:{type(exc).__name__}")

    return HealthResponse(status="healthy", database="postgresql")
