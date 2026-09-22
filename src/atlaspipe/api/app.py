from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

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
    app.include_router(health_router)
    app.include_router(crawl_router)
    app.include_router(pages_router)
    app.include_router(stats_router)
    return app
