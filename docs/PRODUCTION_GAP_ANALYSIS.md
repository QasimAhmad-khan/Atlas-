# Production gap analysis

Audited source: `29ee6c4bb62e93a5b5ea0329e07b3b0993acfd06` (2026-10-14).

| Area | Existing implementation | Required change / risk |
| --- | --- | --- |
| API | FastAPI, health, page queries, crawl submission | Submission has no authentication or shared quota; bound request bodies |
| Frontier | PostgreSQL `SKIP LOCKED`, renewable leases, owner/token fencing, atomic page write and completion | Preserve at-least-once semantics; add queue context and operational visibility |
| Crawler | HTTP timeouts, byte limits, redirects checked, retry budgets, per-domain concurrency | DNS validation and connection resolution are separate; validate connector DNS results |
| Worker | Independent entrypoint, signal stop event | Bound drain time, heartbeat and health probe; renew through persistence |
| Database | Four Alembic migrations, idempotent normalized URL upserts | Additive migrations; private cloud networking and managed secrets |
| Observability | JSON structlog; process-local helper | HTTP/DB/queue/worker Prometheus, trace context across frontier, dashboards and alerts |
| Containers | API and worker image; Compose PostgreSQL | API startup currently migrates; use one-off migration; non-root image |
| CI | PostgreSQL 16 service, migration, Ruff, mypy, pytest | Already integrates PostgreSQL (pasted audit was stale); add lock, migration drift, security and release gates |
| Cloud / delivery | No Terraform or release workflow | ECS/RDS/ECR/ALB/IAM/OIDC, controlled migration, health and rollback evidence |
| Evidence | Original local benchmark JSON and worker death logs | Retain untouched; new measurements must state environment and raw paths |

Baseline on Windows / Python 3.13.5: 33 tests passed, 3 PostgreSQL tests skipped (no DATABASE_URL), Ruff lint and format passed. Strict mypy found one existing nullable status-code mismatch in `db/repositories.py`. An earlier test attempt ran while dependencies were still installing and failed collection; it is not an application test result. Docker, Terraform and GitHub CLI are absent. Portable PostgreSQL is being prepared in ignored workspace files. No AWS resources have been provisioned.

Files to extend: API app/dependencies/crawl, config, schemas, DB models/repositories/session, frontier worker and entrypoint, fetcher, logging; additive migrations; tests; containers; workflows; new telemetry, infrastructure, experiment and runbook files.

## Decisions

Keep FastAPI/PostgreSQL and the durable frontier. Use PostgreSQL atomic quota updates instead of another state service. Use one immutable image for independently deployed API/workers; migrations run separately. Use RDS-managed credentials and retrieve them in the task without exposing plaintext in Terraform. Cloud apply, public deployment and destructive experiments require explicit approval. Single-AZ demo availability is not production HA.

## Original benchmark baseline

`benchmarks/results/` contains the original database, ingestion, domain rollup, PostgreSQL stress and worker-death artifacts. Their claims are historical local evidence, not newly reproduced measurements or AWS results. See `docs/BENCHMARKS.md` for methodology; new evidence uses separate paths.
