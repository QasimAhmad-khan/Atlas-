# Performance report

These are local measurements, not AWS results. Windows, Python 3.13.5, PostgreSQL 17.11, k6 1.3.0, one API process, 10,000 synthetic pages over 100 domains. Five virtual users repeatedly request authenticated /pages?limit=20 and /stats for ten seconds per run. No external crawl traffic. Runs were sequential, with no simultaneous verification suite. The developer host and warm caches may affect the variation. OTLP export to a live backend was disabled; DB spans and metrics remained enabled.

| Run | Requests | RPS | p50 ms | p95 ms | p99 ms | Error rate |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1340 | 133.32 | 36.78 | 44.06 | 62.35 | 0.00% |
| 2 | 1450 | 144.96 | 34.32 | 37.57 | 39.32 | 0.00% |
| 3 | 1320 | 131.15 | 35.24 | 40.73 | 111.77 | 0.00% |

Mean throughput 136.48 RPS; run range 131.15–144.96 RPS; sample standard deviation 7.43 RPS. Three short runs are insufficient for a production capacity or confidence-interval claim. Raw per-run distributions are retained.

Actual API CPU time was 29.73 seconds over 32.49 wall seconds. Working-set endpoint samples were 91.45 and 94.99 MiB; these are not peak-memory measurements. PostgreSQL counter differences were:

```json
{
  "xact_commit": 3988,
  "xact_rollback": 3985,
  "blks_read": 0,
  "blks_hit": 77128,
  "tup_returned": 57782992,
  "tup_fetched": 42982
}
```

Raw evidence: `artifacts/performance/run-1.json` through `run-3.json`, `seed.json`, `api-resources.json`, `before.json`, `after.json` and authenticated `.prom` snapshots. PostgreSQL read-session cleanup rolls back read transactions; the rollback counter is not a count of failed crawl transactions. The high returned-tuple count reflects aggregate scans in this workload and warrants larger-volume profiling before capacity claims.

The separate 200-record worker-death run measured 14.16 completed pages/sec over a deliberately slow failure fixture. That is whole-experiment throughput, not steady-state capacity. The small in-memory ingestion sample is in `ingestion-small.json`; it is not a PostgreSQL or cloud benchmark. Original million-row results remain under `benchmarks/results/` and have not been reproduced at that scale in this upgrade.

## Reproduce

Create a fresh dedicated database named atlaspipe_perf, set DATABASE_URL, then run Alembic and `python benchmarks/seed_api_database.py --rows 10000`. Start the API on localhost:58000 with generated API_KEY and METRICS_KEY values. Set API_KEY in the k6 process environment (avoid secrets in CLI arguments). Run `k6 run -e BASE_URL=http://127.0.0.1:58000 -e OUTPUT=artifacts/performance/run-1.json benchmarks/api_load.js` three times, changing OUTPUT each time. Collect `benchmarks/resource_snapshot.py` before/after using METRICS_KEY and SNAPSHOT_OUTPUT. Repeat on a quiet host for a stronger baseline. Cloud benchmarks and billing measurements are outside this showcase scope.
