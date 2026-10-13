# Database TCP connectivity interrupted

Environment: controlled local PostgreSQL / HTTP fixture, **not AWS**.

## Trigger and timeline

Recorded at 2026-10-13T21:27:45.969527+00:00. The trigger is controlled by the test or worker-death script. Measured durations below cover the recorded detection/recovery or whole experiment; unrecorded intermediate timestamps are not inferred.

## Expected and observed behavior

Expected: bounded failure, safe terminal/retry states and no extra logical persisted record. The passing assertion result and raw observations are:

```json
{
  "environment": "local Windows/POSIX fixture; not AWS",
  "timestamp": "2026-10-13T21:27:45.969527+00:00",
  "passed": true,
  "fault_readiness": 503,
  "liveness": 200,
  "restored_readiness": 200,
  "detection_and_recovery_seconds": 0.1724303000009968,
  "trigger": "close DB TCP connections and reject reconnections in an owned proxy"
}
```

## Root cause and recovery

The owned proxy closed real connections and refused reconnects. Readiness and telemetry degraded while process liveness stayed healthy; reconnecting restored readiness.

Detection used actual DB state, API responses or the connector error category. The assertion result checks the relevant state/integrity invariant; it does not prove global production availability.

## Prevention and limits

Retain atomic writes, fencing, retry budgets, bounded pools and drain limits. Monitor backlog, heartbeat freshness and database/HTTP errors. Run larger sustained profiles and approved AWS experiments separately. Local tests do not verify cloud failover, external notification delivery, RDS restoration or a managed telemetry backend.

Raw evidence: [JSON](../../artifacts/reliability/database-interruption.json).
