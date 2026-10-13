from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import JSONResponse

from atlaspipe.api.routes.crawl import router as crawl_router
from atlaspipe.api.routes.health import router as health_router
from atlaspipe.api.routes.pages import router as pages_router
from atlaspipe.api.routes.stats import router as stats_router
from atlaspipe.config import Settings, get_settings
from atlaspipe.db.repositories import PageRepository
from atlaspipe.db.session import create_engine, create_session_factory
from atlaspipe.observability.logging import configure_logging


def create_app(
    *,
    settings: Settings | None = None,
    repository: PageRepository | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if repository is not None:
            app.state.repository = repository
            yield
            return

        engine = create_engine(resolved_settings)
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title="AtlasPipe",
        version="0.1.0",
        description="Async web metadata ingestion pipeline.",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.quota_lock = asyncio.Lock()
    app.state.test_quota = {}

    @app.middleware("http")
    async def limit_request_body(request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in {"POST", "PUT", "PATCH"}:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > resolved_settings.api_max_body_bytes:
                    return JSONResponse({"detail": "request body too large"}, status_code=413)
            request._body = bytes(body)
        return await call_next(request)

    app.include_router(health_router)
    app.include_router(crawl_router)
    app.include_router(pages_router)
    app.include_router(stats_router)
    return app
