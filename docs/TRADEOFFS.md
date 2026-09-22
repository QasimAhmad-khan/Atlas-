# Trade-offs

## asyncio vs Threads

AtlasPipe uses `asyncio` because the pipeline is I/O-heavy and benefits from many waiting
network operations without tying up a thread per request.

## PostgreSQL vs Document Database

PostgreSQL was chosen because URL lookup, domain filters, status-code aggregates, and
job/attempt relationships map cleanly to relational tables and indexes.

## Batch Inserts vs Single-row Inserts

The code supports batch persistence because ingestion workloads pay avoidable overhead
when every page is written one at a time. The lightweight insert benchmark isolates
application batching overhead, while live PostgreSQL results are reported separately:
asyncpg batch writes reached about 8.6K rows/sec in the 50K test and PostgreSQL `COPY`
reached about 16.6K rows/sec in the 1M-row high-volume run.

## Hash Deduplication vs Semantic Deduplication

Hash deduplication is deterministic and cheap. Near-duplicate text comparison is optional
because it grows more expensive and can produce judgment calls.

## Durable Frontier vs External Queue

AtlasPipe now uses PostgreSQL as the durable crawl frontier rather than adding Celery,
Kafka, or another external queue immediately. That keeps the system reviewable while
still demonstrating the core distributed-worker mechanics: persisted jobs, leases,
lease expiration, retries, dead-letter state, and idempotent writes.

The guarantee is deliberately at-least-once delivery with idempotent storage. Exactly-once
execution is not claimed.

## SQLAlchemy vs Raw SQL

SQLAlchemy keeps the schema and repository code typed and explicit while Alembic manages
migrations. Raw SQL would be useful for future high-volume COPY paths or query-plan
experiments.
