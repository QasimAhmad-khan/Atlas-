from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text

from atlaspipe.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request, response: Response) -> HealthResponse:
    return await ready(request, response)


@router.get("/live", response_model=HealthResponse)
async def live() -> HealthResponse:
    return HealthResponse(status="healthy", database="not_checked")


@router.get("/ready", response_model=HealthResponse)
async def ready(request: Request, response: Response) -> HealthResponse:
    if getattr(request.app.state, "repository", None) is not None:
        return HealthResponse(status="healthy", database="in_memory_repository")

    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="unhealthy", database="not_configured")

    try:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="unhealthy", database=f"unreachable:{type(exc).__name__}")

    return HealthResponse(status="healthy", database="postgresql")
