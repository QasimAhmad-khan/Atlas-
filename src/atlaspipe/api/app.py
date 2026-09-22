from __future__ import annotations

from fastapi import FastAPI

from atlaspipe.api.routes.crawl import router as crawl_router
from atlaspipe.api.routes.health import router as health_router
from atlaspipe.api.routes.pages import router as pages_router
from atlaspipe.api.routes.stats import router as stats_router
from atlaspipe.observability.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging("INFO")
    app = FastAPI(
        title="AtlasPipe",
        version="0.1.0",
        description="Async web metadata ingestion pipeline.",
    )
    app.include_router(health_router)
    app.include_router(crawl_router)
    app.include_router(pages_router)
    app.include_router(stats_router)
    return app
