# Trade-offs

## asyncio vs Threads

AtlasPipe uses `asyncio` because the pipeline is I/O-heavy and benefits from many waiting
network operations without tying up a thread per request.

## PostgreSQL vs Document Database

PostgreSQL was chosen because URL lookup, domain filters, status-code aggregates, and
job/attempt relationships map cleanly to relational tables and indexes.

## Batch Inserts vs Single-row Inserts

The code supports batch persistence because ingestion workloads pay avoidable overhead
when every page is written one at a time. Local benchmark results show batches are much
faster in the in-memory repository; live PostgreSQL measurement remains pending.

## Hash Deduplication vs Semantic Deduplication

Hash deduplication is deterministic and cheap. Near-duplicate text comparison is optional
because it grows more expensive and can produce judgment calls.

## Single Service vs Distributed Queue

The current project stays single-service to keep the implementation reviewable. The
internal boundaries leave room for a queue-backed worker split later.

## SQLAlchemy vs Raw SQL

SQLAlchemy keeps the schema and repository code typed and explicit while Alembic manages
migrations. Raw SQL would be useful for future high-volume COPY paths or query-plan
experiments.
