# Benchmarks

These results were generated locally on 2026-09-22 with Python 3.13.5 on Windows.
PostgreSQL 16.15 was run from the official EDB Windows x64 binary archive under
`C:\atlas\.postgres_runtime` on port `55432`.

Raw machine-readable files:

- `benchmarks/results/ingestion_benchmark.json`
- `benchmarks/results/database_benchmark.json`
- `benchmarks/results/postgres_stress_benchmark.json`
- `benchmarks/results/postgres_high_volume_benchmark.json`
- `benchmarks/results/pgbench_run.txt`
- `benchmarks/results/pgbench_high_volume_run.txt`

## Ingestion Benchmark

| Records | Concurrency | Elapsed seconds | Records/sec |
|---:|---:|---:|---:|
| 100 | 1 | 0.081113 | 1232.84 |
| 100 | 5 | 0.075522 | 1324.12 |
| 100 | 10 | 0.077781 | 1285.66 |
| 1000 | 1 | 0.780026 | 1282.01 |
| 1000 | 5 | 0.760966 | 1314.12 |
| 1000 | 10 | 0.781861 | 1279.0 |

## Insert Benchmark

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

Measured query latency averages at 1.822M `pages` rows:

| Query | Avg ms | Min ms | Max ms |
|---|---:|---:|---:|
| lookup by normalized URL | 1.833 | 0.272 | 10.593 |
| filter by domain and recent order | 0.965 | 0.513 | 3.105 |
| recent pages | 0.491 | 0.365 | 0.870 |
| status-code filter | 0.546 | 0.448 | 0.964 |
| domain aggregate | 720.615 | 665.216 | 954.041 |

`EXPLAIN ANALYZE` still showed a direct index scan for normalized URL lookup with 0.039 ms
execution time. The domain/recent query used an index scan backward on `ix_pages_created_at`
and returned 100 rows in 0.080 ms. The domain aggregate became the expensive query, using
a parallel sequential scan over the 1.8M-row table and completing in 723.389 ms.

Measured query latency averages:

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
