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
URLs -> API/scheduler -> PostgreSQL crawl_frontier
     -> leased workers -> fetcher -> parser -> normalizer
     -> idempotent writer -> repository/PostgreSQL -> FastAPI
```

The original in-process pipeline still uses bounded queues for controlled fixture runs.
The V2 worker path adds a durable PostgreSQL frontier. Workers claim work with expiring
leases, so abandoned work can be recovered by another worker after a crash. Page storage
is idempotent on `normalized_url`, which supports at-least-once delivery without creating
duplicate logical page records.

Global request rate is controlled by a token bucket, while per-domain concurrency uses
domain-keyed semaphores.

## Boundaries

The process can still run as one service for review. The durable frontier now allows a
deployment to split API submission and worker execution without rewriting parser,
normalizer, deduplicator, or repository code.

## Frontier Semantics

The frontier is intentionally honest about distributed-system guarantees:

- Delivery is at least once.
- Each lease has an owner and expiration time.
- Expired leases become claimable by another worker.
- Failed work is retried until `max_attempts`, then moved to `dead`.
- Page writes are idempotent on normalized URL.

AtlasPipe does not claim exactly-once execution.

## Scaling Path

At 100K pages, this architecture can run locally with PostgreSQL-backed workers. The
first measured million-row query bottleneck, domain aggregation, now has a
`domain_stats` rollup path so read requests can avoid grouping the large `pages` table.

At 10M pages, raw HTML should move to object storage and additional aggregate queries
should use measured rollups or materialized views. At 1B pages, the system would need
stronger distributed scheduling, database partitioning where measured to help, separate
search infrastructure, and more complete crawl politeness infrastructure.
