from __future__ import annotations

from fastapi import FastAPI

from atlaspipe.api.routes.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="AtlasPipe",
        version="0.1.0",
        description="Async web metadata ingestion pipeline.",
    )
    app.include_router(health_router)
    return app
