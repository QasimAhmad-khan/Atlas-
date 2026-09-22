# Benchmarks

These results were recorded locally on 2026-09-22 with Python 3.13.5 on Windows.
PostgreSQL 16.15 was run from the official EDB Windows x64 binary archive under
`C:\atlas\.postgres_runtime` on port `55432`.

## Environment

| Item | Value |
|---|---|
| CPU | Intel Core i7-9850H, 6 cores / 12 logical processors |
| RAM | 34,064,666,624 bytes, about 31.7 GiB |
| Storage | PC601 NVMe SK hynix 512GB SSD |
| OS | Windows |
| Python | 3.13.5 |
| PostgreSQL | 16.15, portable EDB Windows x64 runtime |
| PostgreSQL port | 55432 |
| `shared_buffers` | 128MB |
| `work_mem` | 4MB |
| `maintenance_work_mem` | 64MB |
| `effective_cache_size` | 4GB |
| `max_connections` | 250 for the high-concurrency pgbench retest |

Raw machine-readable files:

- `benchmarks/results/ingestion_benchmark.json`
- `benchmarks/results/database_benchmark.json`
- `benchmarks/results/postgres_stress_benchmark.json`
- `benchmarks/results/postgres_high_volume_benchmark.json`
- `benchmarks/results/pgbench_run.txt`
- `benchmarks/results/pgbench_high_volume_run.txt`

## Ingestion Benchmark

This benchmark uses controlled fixture pages and a synthetic fetcher, so it exercises the
AtlasPipe software path without hitting public websites: fetch response object creation,
HTML parsing, URL normalization, hashing, deduplication, batching, and repository writes.
Latency is measured from fixture fetch start through batch save.

| Records | Concurrency | Elapsed seconds | Records/sec | p50 ms | p95 ms | Peak MB | Failed |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10000 | 1 | 7.630248 | 1310.57 | 186.948 | 356.285 | 105.70 | 0 |
| 10000 | 5 | 7.369599 | 1356.93 | 181.930 | 345.750 | 105.70 | 0 |
| 10000 | 10 | 7.738867 | 1292.18 | 187.910 | 356.457 | 107.01 | 0 |
| 10000 | 25 | 7.598843 | 1315.99 | 180.678 | 347.537 | 107.16 | 0 |
| 10000 | 50 | 7.340558 | 1362.29 | 179.744 | 344.514 | 106.48 | 0 |
| 50000 | 1 | 38.646022 | 1293.79 | 186.651 | 355.219 | 252.32 | 0 |
| 50000 | 5 | 37.626688 | 1328.84 | 181.926 | 346.796 | 252.57 | 0 |
| 50000 | 10 | 37.511434 | 1332.93 | 181.434 | 346.150 | 253.24 | 0 |
| 50000 | 25 | 38.105214 | 1312.16 | 183.225 | 348.137 | 251.23 | 0 |
| 50000 | 50 | 38.139783 | 1310.97 | 184.364 | 350.305 | 252.73 | 0 |
| 100000 | 1 | 82.182589 | 1216.80 | 195.012 | 370.264 | 432.94 | 0 |
| 100000 | 5 | 78.959790 | 1266.47 | 188.861 | 357.047 | 431.05 | 0 |
| 100000 | 10 | 79.667460 | 1255.22 | 188.606 | 357.952 | 433.07 | 0 |
| 100000 | 25 | 80.362986 | 1244.35 | 189.143 | 359.853 | 433.73 | 0 |
| 100000 | 50 | 78.260737 | 1277.78 | 186.221 | 353.450 | 431.32 | 0 |

## Insert Benchmark

The lightweight insert benchmark isolates batching overhead in the in-memory repository.
It is useful for comparing single-row versus batched write paths inside the application,
but it should not be interpreted as live PostgreSQL throughput. Live database performance
is reported separately in the PostgreSQL sections below.

| Records | Mode | Batch size | Insert seconds | Records/sec |
|---:|---|---:|---:|---:|
| 100 | single_row | 1 | 0.001123 | 89007.57 |
| 100 | batch | 100 | 0.000463 | 216029.36 |
| 1000 | single_row | 1 | 0.044453 | 22495.82 |
| 1000 | batch | 100 | 0.005295 | 188864.55 |
| 10000 | single_row | 1 | 4.930653 | 2028.13 |
| 10000 | batch | 100 | 0.114415 | 87401.05 |

## Live PostgreSQL Stress Benchmark

The live PostgreSQL stress benchmark inserted synthetic `pages` records through asyncpg
against the migrated AtlasPipe schema. After the run, the `pages` table contained 122,000
rows and the database size was 113 MB.

| Records | Mode | Batch size | Elapsed seconds | Records/sec |
|---:|---|---:|---:|---:|
| 1000 | single_row | 1 | 0.357434 | 2797.72 |
| 1000 | batch_executemany | 500 | 0.183533 | 5448.62 |
| 10000 | single_row | 1 | 3.624259 | 2759.18 |
| 10000 | batch_executemany | 500 | 1.276222 | 7835.63 |
| 50000 | single_row | 1 | 17.025987 | 2936.69 |
| 50000 | batch_executemany | 500 | 5.802174 | 8617.46 |

## High-volume PostgreSQL COPY Benchmark

The higher-volume retest used PostgreSQL `COPY` through asyncpg while maintaining the
real AtlasPipe `pages` indexes. This pushed the table to 1,822,000 rows and the database
to 2,273 MB.

| Records | Mode | Chunk size | Elapsed seconds | Records/sec |
|---:|---|---:|---:|---:|
| 100000 | copy_records_to_table | 50000 | 6.102576 | 16386.52 |
| 500000 | copy_records_to_table | 50000 | 28.584251 | 17492.15 |
| 1000000 | copy_records_to_table | 50000 | 60.274731 | 16590.70 |

### Query latency at 1.822M rows

| Query | Avg ms | Min ms | Max ms |
|---|---:|---:|---:|
| lookup by normalized URL | 1.833 | 0.272 | 10.593 |
| filter by domain and recent order | 0.965 | 0.513 | 3.105 |
| recent pages | 0.491 | 0.365 | 0.870 |
| status-code filter | 0.546 | 0.448 | 0.964 |
| domain aggregate | 720.615 | 665.216 | 954.041 |

`EXPLAIN ANALYZE` showed a direct index scan for normalized URL lookup with 0.039 ms
execution time. The domain/recent query used an index scan backward on `ix_pages_created_at`
and returned 100 rows in 0.080 ms. The domain aggregate became the expensive query, using
a parallel sequential scan over the 1.8M-row table and completing in 723.389 ms.

### Query latency at 122K rows

| Query | Avg ms | Min ms | Max ms |
|---|---:|---:|---:|
| lookup by normalized URL | 0.642 | 0.440 | 1.417 |
| filter by domain | 24.592 | 23.720 | 27.386 |
| recent pages | 0.450 | 0.322 | 0.806 |
| status-code filter | 0.608 | 0.514 | 0.974 |
| domain aggregate | 50.674 | 44.204 | 68.201 |

`EXPLAIN ANALYZE` confirmed an index scan on `ix_pages_normalized_url` for URL lookup
with 0.035 ms execution time. Domain filtering used `ix_pages_domain`, scanned 50,000
matching rows, sorted by `created_at`, and completed in 25.410 ms.

## pgbench Transaction Stress

`pgbench` initialized scale factor 5, generating 500,000 account rows, then ran 20 clients
and 4 threads for 30 seconds.

| Metric | Value |
|---|---:|
| Transactions processed | 138091 |
| Failed transactions | 0 |
| TPS | 4664.980543 |
| Average latency | 4.278 ms |
| Latency stddev | 3.477 ms |
| Initial connection time | 409.112 ms |

## High-concurrency pgbench Retest

PostgreSQL was tuned from the default connection limit to `max_connections = 250`, then
`pgbench` was initialized at scale factor 50, producing 5,000,000 account rows. The
benchmark ran with 100 clients and 8 threads for 60 seconds.

| Metric | Value |
|---|---:|
| Transactions processed | 263913 |
| Failed transactions | 0 |
| TPS | 4484.834935 |
| Average latency | 22.223 ms |
| Latency stddev | 46.877 ms |
| Initial connection time | 1400.275 ms |

## Limitations

These numbers come from a local Windows portable PostgreSQL runtime rather than Docker
Compose. Docker verification remains separate.
