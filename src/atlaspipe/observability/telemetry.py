from __future__ import annotations

import hmac
import os
import threading
import time
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi import HTTPException, Request
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    GCCollector,
    Histogram,
    PlatformCollector,
    ProcessCollector,
    generate_latest,
)
from sqlalchemy import and_, func, select
from sqlalchemy.engine import Connection, ExceptionContext
from sqlalchemy.ext.asyncio import AsyncEngine

from atlaspipe.config import Settings
from atlaspipe.db.models import CrawlFrontierItem, WorkerHeartbeat

REGISTRY = CollectorRegistry()
GCCollector(registry=REGISTRY)
PlatformCollector(registry=REGISTRY)
ProcessCollector(registry=REGISTRY)
HTTP_REQUESTS = Counter(
    "atlaspipe_http_requests_total",
    "HTTP responses",
    ["method", "route", "status"],
    registry=REGISTRY,
)
HTTP_LATENCY = Histogram(
    "atlaspipe_http_duration_seconds", "HTTP latency", ["method", "route"], registry=REGISTRY
)
DB_LATENCY = Histogram(
    "atlaspipe_db_query_duration_seconds",
    "Database query latency",
    ["operation"],
    registry=REGISTRY,
)
DB_ERRORS = Counter("atlaspipe_db_errors_total", "Database errors", registry=REGISTRY)
DB_POOL = Gauge(
    "atlaspipe_db_pool_connections", "Pool capacity and usage", ["state"], registry=REGISTRY
)
WORK = Counter(
    "atlaspipe_worker_items_total", "Worker processing outcomes", ["outcome"], registry=REGISTRY
)
RETRIES = Counter("atlaspipe_worker_retries_total", "Fetch retries", registry=REGISTRY)
RECOVERIES = Counter(
    "atlaspipe_lease_recoveries_total", "Expired leases reclaimed", registry=REGISTRY
)
EXHAUSTED = Counter(
    "atlaspipe_retry_exhaustion_total", "Items entering dead state", registry=REGISTRY
)
QUEUE = Gauge("atlaspipe_frontier_items", "Current frontier state", ["state"], registry=REGISTRY)
OLDEST = Gauge("atlaspipe_oldest_pending_seconds", "Oldest pending item age", registry=REGISTRY)
WORKERS = Gauge("atlaspipe_workers", "Worker health counts", ["state"], registry=REGISTRY)
HEARTBEAT_AGE = Gauge(
    "atlaspipe_worker_heartbeat_age_seconds", "Newest heartbeat age", registry=REGISTRY
)
TELEMETRY_UP = Gauge(
    "atlaspipe_telemetry_database_up", "Queue and heartbeat query success", registry=REGISTRY
)
_provider: TracerProvider | None = None


def configure_tracing(settings: Settings, service: str) -> None:
    global _provider
    if _provider is not None:
        return
    _provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": f"atlaspipe-{service}",
                "deployment.environment.name": settings.environment,
                "service.version": settings.release,
            }
        )
    )
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(_provider)


def trace_id() -> str | None:
    context = trace.get_current_span().get_span_context()
    return f"{context.trace_id:032x}" if context.is_valid else None


def authorize_metrics(request: Request, settings: Settings) -> None:
    import hmac

    key = settings.metrics_key.get_secret_value()
    actual = request.headers.get("authorization", "")
    if not key or not hmac.compare_digest(actual.encode(), f"Bearer {key}".encode()):
        raise HTTPException(401, "metrics credential required")


async def refresh_queue_metrics(engine: AsyncEngine, settings: Settings) -> None:
    now = datetime.now(UTC)
    stale = now - timedelta(seconds=settings.worker_stale_seconds)
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(CrawlFrontierItem.state, func.count()).group_by(CrawlFrontierItem.state)
            )
        ).all()
        counts = dict(rows)
        for state in ("pending", "leased", "complete", "failed", "dead"):
            QUEUE.labels(state).set(counts.get(state, 0))
        oldest = await connection.scalar(
            select(func.min(CrawlFrontierItem.created_at)).where(
                CrawlFrontierItem.state == "pending"
            )
        )
        OLDEST.set(max(0, (now - oldest).total_seconds()) if oldest else 0)
        owned = (
            select(CrawlFrontierItem.id)
            .where(
                and_(
                    CrawlFrontierItem.state == "leased",
                    CrawlFrontierItem.lease_owner == WorkerHeartbeat.worker_id,
                )
            )
            .exists()
        )
        WORKERS.labels("active").set(
            await connection.scalar(
                select(func.count())
                .select_from(WorkerHeartbeat)
                .where(WorkerHeartbeat.seen_at >= stale)
            )
            or 0
        )
        WORKERS.labels("failed").set(
            await connection.scalar(
                select(func.count())
                .select_from(WorkerHeartbeat)
                .where(WorkerHeartbeat.seen_at < stale, owned)
            )
            or 0
        )
        WORKERS.labels("stalled").set(
            await connection.scalar(
                select(func.count())
                .select_from(WorkerHeartbeat)
                .where(
                    WorkerHeartbeat.seen_at >= stale,
                    WorkerHeartbeat.progress_at < now - timedelta(seconds=120),
                    owned,
                )
            )
            or 0
        )
        newest = await connection.scalar(select(func.max(WorkerHeartbeat.seen_at)))
        HEARTBEAT_AGE.set(
            max(0, (now - newest).total_seconds()) if newest else settings.worker_stale_seconds + 1
        )
    TELEMETRY_UP.set(1)


def pool_metrics(engine: AsyncEngine) -> None:
    pool = engine.sync_engine.pool
    DB_POOL.labels("checked_out").set(pool.checkedout())  # type: ignore[attr-defined]
    DB_POOL.labels("capacity").set(pool.size())  # type: ignore[attr-defined]


def instrument_database(engine: AsyncEngine) -> None:
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def before(
        connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _many: bool,
    ) -> None:
        operation = statement.split(None, 1)[0].upper() if statement.strip() else "OTHER"
        if operation not in {"SELECT", "INSERT", "UPDATE", "DELETE"}:
            operation = "OTHER"
        span = trace.get_tracer("atlaspipe").start_span(
            "db.query",
            kind=trace.SpanKind.CLIENT,
            attributes={"db.system.name": "postgresql", "db.operation.name": operation},
        )
        connection.info["atlaspipe_query"] = (time.perf_counter(), operation, span)

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def after(connection: Connection, *_args: object) -> None:
        entry = connection.info.pop("atlaspipe_query", None)
        if entry is not None:
            started, operation, span = entry
            DB_LATENCY.labels(operation).observe(time.perf_counter() - started)
            span.end()

    @event.listens_for(engine.sync_engine, "handle_error")
    def error(context: ExceptionContext) -> None:
        DB_ERRORS.inc()
        if context.connection is not None:
            entry = context.connection.info.pop("atlaspipe_query", None)
            if entry is not None:
                started, operation, span = entry
                DB_LATENCY.labels(operation).observe(time.perf_counter() - started)
                span.set_attribute("error.type", type(context.original_exception).__name__)
                span.set_status(trace.StatusCode.ERROR)
                span.end()


def start_worker_metrics(settings: Settings, engine: AsyncEngine) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            key = settings.metrics_key.get_secret_value()
            if self.path != "/internal/metrics":
                self.send_error(404)
                return
            if not key or not hmac.compare_digest(
                self.headers.get("Authorization", "").encode(),
                f"Bearer {key}".encode(),
            ):
                self.send_error(401)
                return
            pool_metrics(engine)
            data = generate_latest(REGISTRY)
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("0.0.0.0", settings.worker_metrics_port), Handler)  # noqa: S104
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
