# Controlled downstream slow response

Environment: controlled local PostgreSQL / HTTP fixture, **not AWS**.

## Trigger and timeline

Recorded at 2026-10-13T21:27:45.292097+00:00. The trigger is controlled by the test or worker-death script. Measured durations below cover the recorded detection/recovery or whole experiment; unrecorded intermediate timestamps are not inferred.

## Expected and observed behavior

Expected: bounded failure, safe terminal/retry states and no extra logical persisted record. The passing assertion result and raw observations are:

```json
{
  "environment": "local Windows/POSIX fixture; not AWS",
  "timestamp": "2026-10-13T21:27:45.292097+00:00",
  "passed": true,
  "attempts": 2,
  "logical_pages": 0,
  "frontier": {
    "pending": 0,
    "leased": 0,
    "complete": 0,
    "failed": 0,
    "dead": 1
  },
  "duration_seconds": 0.3135352999997849,
  "max_fetch_attempts": 4
}
```

## Root cause and recovery

The fixture consistently failed. Fetch retry and durable attempt budgets were exhausted and the item entered dead state instead of retrying forever.

Detection used actual DB state, API responses or the connector error category. The assertion result checks the relevant state/integrity invariant; it does not prove global production availability.

## Prevention and limits

Retain atomic writes, fencing, retry budgets, bounded pools and drain limits. Monitor backlog, heartbeat freshness and database/HTTP errors. Run larger sustained profiles and approved AWS experiments separately. Local tests do not verify cloud failover, external notification delivery, RDS restoration or a managed telemetry backend.

Raw evidence: [JSON](../../artifacts/reliability/downstream-slow.json).
