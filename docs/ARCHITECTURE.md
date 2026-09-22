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
leases and lease tokens, so abandoned work can be recovered by another worker after a
crash while stale workers are fenced from completing work they no longer own. Page
storage is idempotent on `normalized_url`, which supports at-least-once delivery without
creating duplicate logical page records.

Workers claim no more rows than they can execute concurrently, then replenish on the next
loop. Successful page persistence and frontier completion are fenced together in one
transaction: the worker must still own the live lease before page metadata is written.
While a healthy worker is processing a long response or honoring a retry delay, it renews
the lease with the same owner/token fence. If renewal fails, the later completion/failure
write is still rejected by the same fencing rule.

Global request rate is controlled by a token bucket, while per-domain concurrency uses
domain-keyed semaphores. The worker retries transient HTTP statuses (`429`, `500`,
`502`, `503`, `504`) with exponential backoff and honors `Retry-After` when present.
Network fetches validate DNS-resolved targets and each redirect hop before requesting the
next URL, so redirects to private or metadata addresses are blocked.

## Boundaries

Docker Compose runs PostgreSQL, the FastAPI control API, and a separate worker process.
The durable frontier allows API submission and worker execution to remain split without
rewriting parser, normalizer, deduplicator, or repository code.

## Frontier Semantics

The frontier is intentionally honest about distributed-system guarantees:

- Delivery is at least once.
- Each lease has an owner, token, and expiration time.
- Expired leases become claimable by another worker.
- Healthy workers renew long-lived leases with the same owner/token fence.
- Completion and failure updates require matching `id`, `lease_owner`, `lease_token`, and
  `state='leased'`.
- Successful page writes are coupled with fenced completion in one transaction.
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
