# Benchmarks

These results were generated locally on 2026-09-22 with Python 3.13.5 on Windows. Docker
and PostgreSQL were unavailable, so these are deterministic in-memory pipeline and
repository benchmarks, not live PostgreSQL benchmarks.

Raw machine-readable files:

- `benchmarks/results/ingestion_benchmark.json`
- `benchmarks/results/database_benchmark.json`

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

## Limitations

These numbers measure local Python pipeline overhead and repository behavior. They should
not be presented as PostgreSQL throughput. Live database benchmarks should be rerun once
Docker or PostgreSQL is available.
