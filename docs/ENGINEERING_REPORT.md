# AtlasPipe: Scaling an Async Data Pipeline Until It Breaks

## 1. Initial Architecture

AtlasPipe began as a bounded asynchronous ingestion pipeline:

```text
URLs -> bounded queue -> fetch -> parse -> normalize -> dedupe -> batch write -> PostgreSQL
```

That shape was enough to test parsing, normalization, deduplication, batch persistence,
FastAPI query surfaces, and PostgreSQL indexing. It was not enough to make strong claims
about distributed execution because work lived inside one process.

## 2. Baseline Measurements

The first measurement pass separated benchmark classes:

- Synthetic in-memory insert benchmark
- Controlled full-pipeline fixture benchmark
- Live PostgreSQL ingestion benchmark
- PostgreSQL-only `pgbench` stress test

The strongest live database result so far is 1.82M persisted `pages` rows, about 16.6K
rows/sec through PostgreSQL `COPY`, sub-2 ms indexed URL lookup, and zero failed
transactions in a 100-client `pgbench` stress test.

## 3. First Bottleneck

The high-volume query suite exposed one clear expensive query: domain aggregation over
1.82M rows took about 720 ms and used a parallel sequential scan. That result is kept in
the benchmark docs because it is useful evidence, not something to hide.

## 4. Distributed Frontier Design

V2 adds a PostgreSQL-backed `crawl_frontier` table. It stores each unit of crawl work with
state, priority, attempts, lease owner, lease token, lease expiry, availability time, and error
metadata.

Workers claim work with `FOR UPDATE SKIP LOCKED` semantics in the SQLAlchemy repository.
The important guarantee is:

- Delivery: at least once
- Storage: idempotent on normalized URL

Exactly-once execution is not claimed.

## 5. Worker Failure Semantics

If a worker dies after leasing work, that work remains `leased` until
`lease_expires_at`. Another worker can then acquire it and increment `attempt_count`.
Failures retry until `max_attempts`, then move to `dead`. Completion and failure updates
are fenced by `lease_owner` and `lease_token`, so a stale worker cannot complete a lease
that has already expired and been acquired by another worker.

The worker also avoids pre-claiming a large backlog. It claims at most its available
execution concurrency and then replenishes on the next loop, which reduces the chance
that queued-but-not-yet-executing work expires before it starts. On success, page
persistence and frontier completion happen as one fenced transaction; if the lease is
stale, the page write is skipped. Healthy workers also renew long-running leases with
the same owner/token fence, so a slow response or long `Retry-After` delay does not
unnecessarily hand work to another worker.

The PostgreSQL recovery demo scheduled 10,000 records, abandoned 500 leases, expired them
in PostgreSQL, and ran four SQL-backed workers. Final result:

- Scheduled: 10,000
- SQL-backed workers: 4
- Expired leases recovered: 500
- Completed: 10,000
- Stale completions rejected: 1
- Lost records: 0
- Logical pages persisted: 10,000

The next operational proof is `scripts/postgres_worker_death_demo.py`, which starts real
worker processes, kills one process while it owns live leases, lets those leases expire
naturally, and records the recovery result to
`benchmarks/results/postgres_worker_death_demo.json`.

## 6. Database Scaling

PostgreSQL is still the right metadata store for the current workload because normalized
URL lookup, domain filtering, job accounting, attempts, and status-code aggregates are
relational and index-friendly.

The project already distinguishes single-row inserts, asyncpg batched inserts, and
PostgreSQL `COPY`. The next scaling step is not to claim unlimited PostgreSQL throughput;
it is to isolate which queries need rollups, materialized views, partial indexes, or
different data layout.

## 7. Backpressure

The original in-process pipeline uses bounded queues. The durable-worker path adds fixed
lease batch sizes and worker concurrency limits. That means producers can create durable
work faster than workers consume it without forcing unbounded in-process memory growth.

The next experiment should deliberately slow persistence and record queue depth, worker
throughput, and process RSS over time.

## 8. Aggregate-query Failure

The domain aggregate was the clearest database bottleneck. The investigation path was:

```text
baseline benchmark -> EXPLAIN ANALYZE -> candidate designs -> implementation -> rebenchmark
```

The implemented design is a `domain_stats` rollup table refreshed from `pages`.
On the 1.822M-row local dataset, the latest warmed benchmark measured:

- Baseline grouped aggregate: 230.7 ms average
- Rollup lookup: 1.09 ms average
- Rollup refresh: 3.08 seconds

The earlier high-volume benchmark recorded the same aggregate class around 720 ms. The
new result is not presented as magic; it moves the cost from every read request to an
explicit refresh step.

## 9. Chaos Testing

The first chaos-style proof is PostgreSQL lease recovery with stale-completion fencing.
The worker-death demo extends that from simulated lease abandonment to an actual killed
worker process. A fuller suite should still add:

- worker death after fetch but before persistence
- worker death after persistence but before completion ACK
- database unavailability during writes
- HTTP 429/500/503/timeouts
- malformed and oversized HTML
- redirect loops and private-network redirects
- poison tasks moving to dead-letter state

## 10. Remaining Limitations

AtlasPipe is still a laptop-scale portfolio system, not an internet-scale crawler. Raw
HTML storage is not yet separated into object storage, rollup freshness policy is still
manual, and canonical V2 benchmarks should move to Linux/Docker for reviewer
reproducibility.

Those limits are documented because they are part of the engineering story: measure,
identify the actual bottleneck, change one thing, and measure again.
