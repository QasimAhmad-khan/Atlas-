# Process killed after transaction commit

Environment: controlled local PostgreSQL / HTTP fixture, **not AWS**.

## Trigger and timeline

Recorded at 2026-10-13T21:27:44.283073+00:00. The trigger is controlled by the test or worker-death script. Measured durations below cover the recorded detection/recovery or whole experiment; unrecorded intermediate timestamps are not inferred.

## Expected and observed behavior

Expected: bounded failure, safe terminal/retry states and no extra logical persisted record. The passing assertion result and raw observations are:

```json
{
  "environment": "local Windows/POSIX fixture; not AWS",
  "timestamp": "2026-10-13T21:27:44.283073+00:00",
  "passed": true,
  "page_count_before_kill": 1,
  "logical_records_after_recovery": 1,
  "attempts": 1,
  "frontier": {
    "pending": 0,
    "leased": 0,
    "complete": 1,
    "failed": 0,
    "dead": 0
  },
  "recovery_seconds": 0.03185400000074878,
  "trigger": "actual child process kill at controlled transaction boundary"
}
```

## Root cause and recovery

Committed completion prevents another claim. The existing normalized-URL record remains the single logical persisted record.

Detection used actual DB state, API responses or the connector error category. The assertion result checks the relevant state/integrity invariant; it does not prove global production availability.

## Prevention and limits

Retain atomic writes, fencing, retry budgets, bounded pools and drain limits. Monitor backlog, heartbeat freshness and database/HTTP errors. Run larger sustained profiles and approved AWS experiments separately. Local tests do not verify cloud failover, external notification delivery, RDS restoration or a managed telemetry backend.

Raw evidence: [JSON](../../artifacts/reliability/after_commit.json).
