# Architecture

AtlasPipe is organized around replaceable boundaries:

- `crawler`: HTTP fetching, retry classification, robots placeholder, and rate limiting.
- `parsing`: HTML metadata, links, email domains, and technology hints.
- `pipeline`: URL normalization, validation, deduplication, and bounded worker flow.
- `db`: SQLAlchemy models, Alembic migrations, repositories, and query helpers.
- `api`: FastAPI routes and dependency wiring.
- `observability`: structured logging and metrics counters.

## Data Flow

```text
URLs -> bounded queue -> workers -> fetcher -> parser -> normalizer
     -> deduplicator -> batch writer -> repository/PostgreSQL -> FastAPI
```

The worker pool is fixed by `MAX_CONCURRENCY`, and the queue has a bounded max size to
avoid unbounded task creation. Global request rate is controlled by a token bucket, while
per-domain concurrency uses domain-keyed semaphores.

## Boundaries

The current process can run as one service. The interfaces are intentionally shaped so a
future deployment can split the API and crawler workers without rewriting parser,
normalizer, deduplicator, or repository code.

## Scaling Path

At 100K pages, this architecture can stay single-service with better batch tuning and
PostgreSQL indexes. At 10M pages, crawling should move to queue-backed workers with
partitioned job ownership and object storage for raw HTML. At 1B pages, the system would
need distributed scheduling, Kafka-like ingestion, database partitioning, separate search
infrastructure, and stronger crawl politeness infrastructure.
