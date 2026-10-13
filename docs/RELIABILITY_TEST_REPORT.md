# Reliability test report

The final local suite passed 73 tests, including 11 PostgreSQL/HTTP fault tests. Raw JUnit is `artifacts/tests.xml`; per-scenario JSON and the earlier dedicated worker-death result are under `artifacts/reliability/`. Individual RCAs are under `docs/INCIDENT_REPORTS/`.

| Required scenario | Local evidence | AWS status |
| --- | --- | --- |
| A Worker killed with leases | Actual two-process test: 200/200 completed; 4/4 leases recovered; zero lost/duplicate logical records | Unverified |
| B Killed after fetch | Actual child process kill, natural expiry, one recovered page | Unverified |
| C Persistence/completion boundary | Actual kills during uncommitted write and after commit; one logical page in both cases | Unverified |
| D DB interruption | Owned TCP proxy closes/refuses real connections: ready 503, live 200, then ready 200 and metrics up | Unverified |
| E Pool exhaustion | Actual one-connection pool timeout and recovery | Unverified |
| F 429/500/503/timeouts | Owned HTTP fixtures; bounded fetch attempts and two durable attempts | Unverified |
| G Poison work | Terminal dead state after exhaustion, no successful page | Unverified |
| H Broken release | Release-controller mock response tests and protected workflow prepared | Actual cloud rollback unverified |
| I Overload/unauthorized | Atomic quota across two API instances: 3 accepted, 9 rejected; auth/body tests | WAF behavior unverified |
| J Graceful termination | Shared stop-event drains real in-flight job; stuck task cancelled by deadline | POSIX SIGTERM and ECS stop unverified |

Prometheus's rule test confirms synthetic alert firing and resolution. Actual database health metrics also degrade/recover under a network fault. A running collector/Grafana alert notification was not tested; these are distinct checks. Stale fencing and idempotent persistence are covered by real PostgreSQL tests. The suite does not claim exactly-once execution.

Run with a fresh dedicated test database: `uv run --frozen alembic upgrade head`, then `uv run --frozen pytest --junitxml=artifacts/tests.xml`. The test database must not contain unrelated pending crawl jobs; fixture workers acquire from the shared frontier. The 200-record death experiment is `python scripts/postgres_worker_death_demo.py --records 200 --workers 2 --worker-concurrency 4 --batch-size 4 --lease-seconds 2 --slow-records 8 --slow-delay-seconds 3 --kill-after-seconds 2 --timeout-seconds 60 --output artifacts/reliability/worker-death.json`.

For an approved cloud experiment, record actual release events, task image digests, notification times and data queries. Restore an RDS snapshot to a new private isolated instance, supply fresh access controls/secrets, verify row counts and API behavior without changing the live dataset, then remove the approved temporary instance. Snapshot restoration has not been run.
