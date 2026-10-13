from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response
from opentelemetry import trace
from opentelemetry.propagate import extract
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
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
from atlaspipe.observability.telemetry import (
    HTTP_LATENCY,
    HTTP_REQUESTS,
    REGISTRY,
    TELEMETRY_UP,
    authorize_metrics,
    configure_tracing,
    pool_metrics,
    refresh_queue_metrics,
    trace_id,
)


def create_app(
    *,
    settings: Settings | None = None,
    repository: PageRepository | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    configure_tracing(resolved_settings, "api")

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

    @app.middleware("http")
    async def observe(request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = time.perf_counter()
        supplied_id = request.headers.get("x-request-id", "")
        request_id = (
            supplied_id if re.fullmatch(r"[a-zA-Z0-9._-]{1,64}", supplied_id) else uuid4().hex
        )
        status_code = 500
        method = (
            request.method
            if request.method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
            else "OTHER"
        )
        with trace.get_tracer("atlaspipe").start_as_current_span(
            "http.request",
            context=extract(dict(request.headers)),
            kind=trace.SpanKind.SERVER,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            with structlog.contextvars.bound_contextvars(
                service="api",
                environment=resolved_settings.environment,
                release=resolved_settings.release,
                request_id=request_id,
                trace_id=trace_id(),
                job_id=None,
                worker_id=None,
            ):
                try:
                    response = await call_next(request)
                    status_code = response.status_code
                    response.headers["X-Request-ID"] = request_id
                    if trace_id():
                        response.headers["X-Trace-ID"] = trace_id() or ""
                    return response
                except Exception as exc:
                    span.set_attribute("error.type", type(exc).__name__)
                    span.set_status(trace.StatusCode.ERROR)
                    structlog.get_logger().error("http.failed", error_category=type(exc).__name__)
                    raise
                finally:
                    route = getattr(request.scope.get("route"), "path", "unmatched")
                    elapsed = time.perf_counter() - started
                    span.set_attribute("http.route", route)
                    span.set_attribute("http.response.status_code", status_code)
                    if status_code >= 500:
                        span.set_status(trace.StatusCode.ERROR)
                    HTTP_REQUESTS.labels(method, route, str(status_code)).inc()
                    HTTP_LATENCY.labels(method, route).observe(elapsed)
                    structlog.get_logger().info(
                        "http.completed", route=route, status=status_code, duration=elapsed
                    )

    @app.get("/internal/metrics", include_in_schema=False)
    async def metrics(request: Request) -> Response:
        authorize_metrics(request, resolved_settings)
        if repository is None:
            try:
                await refresh_queue_metrics(app.state.engine, resolved_settings)
                pool_metrics(app.state.engine)
            except Exception:
                TELEMETRY_UP.set(0)
        return Response(generate_latest(REGISTRY), headers={"Content-Type": CONTENT_TYPE_LATEST})

    app.include_router(health_router)
    app.include_router(crawl_router)
    app.include_router(pages_router)
    app.include_router(stats_router)
    return app
