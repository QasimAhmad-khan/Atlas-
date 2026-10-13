# Stop event during a real in-flight fetch

Environment: controlled local PostgreSQL / HTTP fixture, **not AWS**.

## Trigger and timeline

Recorded at 2026-10-13T21:27:46.356694+00:00. The trigger is controlled by the test or worker-death script. Measured durations below cover the recorded detection/recovery or whole experiment; unrecorded intermediate timestamps are not inferred.

## Expected and observed behavior

Expected: bounded failure, safe terminal/retry states and no extra logical persisted record. The passing assertion result and raw observations are:

```json
{
  "environment": "local Windows/POSIX fixture; not AWS",
  "timestamp": "2026-10-13T21:27:46.356694+00:00",
  "passed": true,
  "frontier": {
    "pending": 0,
    "leased": 0,
    "complete": 1,
    "failed": 0,
    "dead": 0
  },
  "drain_seconds": 0.23808920000010403,
  "trigger": "shared signal stop event; actual POSIX SIGTERM delivery unverified on Windows"
}
```

## Root cause and recovery

The shared shutdown path stopped new claims and allowed the in-flight request and transaction to complete inside the drain budget. POSIX signal delivery itself was not tested on Windows.

Detection used actual DB state, API responses or the connector error category. The assertion result checks the relevant state/integrity invariant; it does not prove global production availability.

## Prevention and limits

Retain atomic writes, fencing, retry budgets, bounded pools and drain limits. Monitor backlog, heartbeat freshness and database/HTTP errors. Run larger sustained profiles and approved AWS experiments separately. Local tests do not verify cloud failover, external notification delivery, RDS restoration or a managed telemetry backend.

Raw evidence: [JSON](../../artifacts/reliability/graceful-drain.json).
