# Actual worker process killed with active leases

Environment: controlled local PostgreSQL / HTTP fixture, **not AWS**.

## Trigger and timeline

Recorded at 2026-10-13T20:47:16.326603+00:00. The trigger is controlled by the test or worker-death script. Measured durations below cover the recorded detection/recovery or whole experiment; unrecorded intermediate timestamps are not inferred.

## Expected and observed behavior

Expected: bounded failure, safe terminal/retry states and no extra logical persisted record. The passing assertion result and raw observations are:

```json
{
  "timestamp_utc": "2026-10-13T20:47:16.326603+00:00",
  "run_id": "33912f11bd044b50bc65c118381aa25e",
  "failure_mode": "real worker process killed while owning PostgreSQL leases",
  "scheduled": 200,
  "completed": 200,
  "dead": 0,
  "pending": 0,
  "leased": 0,
  "worker_processes": 2,
  "workers_killed": 1,
  "killed_worker": "worker-death-33912f11bd044b50bc65c118381aa25e-1",
  "leases_orphaned": 4,
  "leases_recovered": 4,
  "stale_completions_rejected": 0,
  "logical_pages": 200,
  "logical_duplicates": 0,
  "lost": 0,
  "lease_seconds": 2,
  "max_attempts": 10,
  "worker_concurrency": 4,
  "batch_size": 4,
  "elapsed_seconds": 14.12,
  "throughput_pages_per_second": 14.16,
  "notes": [
    "Leases are not manually expired in this experiment.",
    "The killed worker cannot attempt a stale completion; stale fencing is covered by postgres_frontier_recovery_demo.json."
  ]
}
```

## Root cause and recovery

A process death leaves committed leases without an owner. Lease expiry and fencing let the surviving worker reclaim them.

Detection used actual DB state, API responses or the connector error category. The assertion result checks the relevant state/integrity invariant; it does not prove global production availability.

## Prevention and limits

Retain atomic writes, fencing, retry budgets, bounded pools and drain limits. Monitor backlog, heartbeat freshness and database/HTTP errors. Run larger sustained profiles and approved AWS experiments separately. Local tests do not verify cloud failover, external notification delivery, RDS restoration or a managed telemetry backend.

Raw evidence: [JSON](../../artifacts/reliability/worker-death.json).
