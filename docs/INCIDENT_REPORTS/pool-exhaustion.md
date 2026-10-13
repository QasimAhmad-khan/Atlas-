# Connection pool deliberately exhausted

Environment: controlled local PostgreSQL / HTTP fixture, **not AWS**.

## Trigger and timeline

Recorded at 2026-10-13T21:27:45.674462+00:00. The trigger is controlled by the test or worker-death script. Measured durations below cover the recorded detection/recovery or whole experiment; unrecorded intermediate timestamps are not inferred.

## Expected and observed behavior

Expected: bounded failure, safe terminal/retry states and no extra logical persisted record. The passing assertion result and raw observations are:

```json
{
  "environment": "local Windows/POSIX fixture; not AWS",
  "timestamp": "2026-10-13T21:27:45.674462+00:00",
  "passed": true,
  "pool_size": 1,
  "timeout_seconds": 0.05,
  "recovered": true,
  "duration_seconds": 0.23879429999942658
}
```

## Root cause and recovery

One held connection consumed the one-connection test pool. The next checkout timed out; releasing it allowed a query to succeed.

Detection used actual DB state, API responses or the connector error category. The assertion result checks the relevant state/integrity invariant; it does not prove global production availability.

## Prevention and limits

Retain atomic writes, fencing, retry budgets, bounded pools and drain limits. Monitor backlog, heartbeat freshness and database/HTTP errors. Run larger sustained profiles and approved AWS experiments separately. Local tests do not verify cloud failover, external notification delivery, RDS restoration or a managed telemetry backend.

Raw evidence: [JSON](../../artifacts/reliability/pool-exhaustion.json).
