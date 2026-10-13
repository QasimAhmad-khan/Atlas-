# Engineering decisions

1. **Keep the existing platform.** FastAPI/PostgreSQL, durable leases, owner/token fencing and normalized-URL persistence remain. Crawl execution is at least once; persistence is idempotent.
2. **Shared quotas use PostgreSQL.** Atomic insert/update conditions enforce one credential quota across API replicas. No new Redis service is needed. WAF protects public read/write ingress; health checks are separate.
3. **Authenticate data as well as writes.** Submitted URLs can contain sensitive query strings. Read credentials protect data; only write credentials can create jobs. Probes stay usable by ALB/ECS.
4. **Additive schema evolution.** Quota/heartbeat tables and nullable trace context keep old code compatible. Alembic runs in a controlled one-off release task; container restarts do not migrate. Application rollback does not undo schema changes.
5. **Bound the worker lifecycle.** Signal stop prevents new claims; drain has a deadline. Cancellation leaves durable leases recoverable. Lease renewal covers persistence as well as fetch work; transaction locking/fencing prevents stale writes.
6. **Carry queue trace context explicitly.** W3C context lives with the job and enters worker spans. DB spans contain operation/category, never SQL values. Process counters are observations rather than a durable audit ledger; shared queue gauges use max across API replicas.
7. **Least-privilege cloud database access.** Runtime uses TLS-verified IAM login; only the migrator obtains an RDS-managed admin password. Terraform stores secret references, not values. Bootstrap grants only the current application tables and sequence access.
8. **One image, separate services.** API and workers deploy independently with immutable ECR digests. A task-local collector exports to a managed telemetry backend, while the complete local stack is reproducible with Compose.
9. **Prove the requested revision.** ECS stability can mean automatic rollback succeeded. The release controller checks PRIMARY task revisions and replica counts, then authenticated job smoke tests; failure restores both previous services.
10. **Report evidence honestly.** Local fixtures, mocked AWS configuration/controller tests, historical benchmark claims and actual AWS runs are separate categories. Real cloud apply, spending, destructive teardown and public deployment require owner approval.
