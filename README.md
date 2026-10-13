# AtlasPipe

## Engineering showcase — verification status

Authenticated job submission, shared PostgreSQL quotas, DNS-safe fetching, worker health/drain,
Prometheus metrics and API → queue → worker → persistence tracing are implemented. The local
PostgreSQL suite passed **73 tests**. A real worker-death fixture completed **200/200 records**,
recovered **4/4 orphaned leases**, and found no lost or duplicate logical records.

Terraform and protected GitHub release workflows are prepared, with private RDS, independent
ECS services, HTTPS, IAM database login, OIDC, ingress limiting and rollback verification.
Terraform validation/security plan tests, Prometheus rule tests and workflow lint passed.
**AWS account configuration and deployment are outside this showcase's scope. No AWS resources
have been provisioned. Remote CI, image scans and the full Compose/Tempo stack remain unverified.**

The dashboard below is an actual local Grafana 12.2.1 capture using Prometheus 3.5.0, authenticated
API traffic and a running worker. Five-minute rate charts smooth a short traffic burst; the
performance report contains the separately measured k6 results.

![Live local Grafana dashboard](artifacts/observability/grafana-api.jpg)

[Worker health](artifacts/observability/grafana-worker.jpg) and
[database panels](artifacts/observability/grafana-db.jpg).

See [implementation status](docs/IMPLEMENTATION_STATUS.md),
[upgrade report](docs/IMPLEMENTATION_REPORT.md), [AWS architecture](docs/AWS_ARCHITECTURE.md),
[deployment](docs/DEPLOYMENT_RUNBOOK.md), [rollback](docs/ROLLBACK_RUNBOOK.md),
[observability](docs/OBSERVABILITY.md), [reliability](docs/RELIABILITY_TEST_REPORT.md),
[performance](docs/PERFORMANCE_REPORT.md), [security](docs/SECURITY_REVIEW.md), and
[cost/teardown](docs/COST_AND_TEARDOWN.md). Measured evidence is in `artifacts/`.
The million-row results below are historical local benchmarks retained from the original repository.

AtlasPipe is an asynchronous Python data-ingestion pipeline for building a structured,
queryable dataset from permitted public web resources. It crawls URLs politely, extracts
web metadata and technographic hints, normalizes and deduplicates records, persists them
to PostgreSQL, and exposes indexed query endpoints through FastAPI.

The project is designed for data-heavy backend work: the kind of engineering behind
company, domain, and technographic datasets where freshness, deduplication, schema design,
rate limits, and query performance matter.

Tested to 1.82M persisted page records with ~16.6K rows/sec PostgreSQL COPY ingestion,
sub-2 ms indexed URL lookup, and zero failed transactions during a 100-client PostgreSQL
stress test. Benchmarked locally on PostgreSQL 16; results and methodology are
reproducible in [docs/BENCHMARKS.md](docs/BENCHMARKS.md).

The known million-row domain aggregate bottleneck was also addressed with a PostgreSQL
rollup table: on the 1.822M-row local dataset, the live aggregate averaged 230.7 ms in
the latest run while the rollup lookup averaged 1.09 ms after refresh.

## Why This Project

MixRank describes its product as a data platform for company, people, job, app, and
technographic data, refreshed frequently and delivered through APIs, warehouse tables,
PostgreSQL, and flat files. AtlasPipe focuses on the lower-level engineering skills behind
that style of system:

- bounded async ingestion
- URL and domain normalization
- content hashing and deduplication
- durable PostgreSQL crawl frontier with leases and retry state
- batch persistence into PostgreSQL
- indexed domain and URL lookup
- API access to structured records
- stress testing with realistic database volumes
- clear trade-offs around correctness, throughput, and crawl safety

It is intentionally not an internet-scale crawler. It is a focused backend/data systems
portfolio project with reproducible tests and benchmarks.

## What It Extracts

For each processed page, AtlasPipe can capture:

- URL, normalized URL, canonical URL, and domain
- page title and meta description
- HTTP status, content type, content length, response latency
- HTML and text/content hashes
- internal, external, and outbound link counts
- detected email domains
- lightweight technology hints
- first-seen, last-seen, created, and updated timestamps

## Architecture

```text
URLs
 |
 v
FastAPI / Scheduler
 |
 v
Durable Crawl Frontier
PostgreSQL jobs / leases / retries
 |
 +-- Worker process
 +-- Worker process
 +-- Worker process
 |
 v
Parser
 |
 v
Normalizer
 |
 v
Deduplicator
 |
 v
Idempotent Page Writer
 |
 v
PostgreSQL
 |
 v
FastAPI
```

## Repository Layout

```text
src/atlaspipe/
  api/              FastAPI app, routes, dependency wiring
  crawler/          aiohttp fetcher, retry policy, frontier worker, rate limiting
  parsing/          HTML metadata, links, email domains, technology hints
  pipeline/         validation, normalization, deduplication, bounded workers
  db/               SQLAlchemy models, repositories, query helpers
  schemas/          Pydantic request/response models
  observability/    structured logging and metrics helpers
migrations/         Alembic PostgreSQL migrations
tests/              unit, API, and pipeline tests
benchmarks/         ingestion, repository, PostgreSQL, and pgbench benchmarks
docs/               architecture, database, pipeline, trade-offs, benchmarks
```

## Development

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install uv==0.13.0
uv sync --frozen --extra dev
python -m pytest
```

One-command local verification and controlled in-memory frontier recovery demo:

```bash
bash scripts/reproduce.sh
```

Optional Nix shell:

```bash
nix develop
```

Windows PowerShell:

```powershell
python -m venv .venv
python -m pip install uv==0.13.0
uv sync --frozen --extra dev
.\.venv\Scripts\python -m pytest
```

Run quality checks:

```powershell
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m ruff format --check .
.\.venv\Scripts\python -m mypy
```

## Docker Quick Start

```powershell
python scripts/configure_local.py
docker compose up --build --wait app worker prometheus collector tempo grafana
```

The compose stack starts PostgreSQL, a one-off migration service, the API and separate workers.
The API waits for the migration service, exposes FastAPI on `http://localhost:8000`, and
uses PostgreSQL by default rather than an in-memory repository.

Apply migrations manually:

```powershell
.\.venv\Scripts\python -m alembic upgrade head
```

Run the controlled in-memory frontier recovery demo:

```powershell
.\.venv\Scripts\python scripts\frontier_recovery_demo.py
```

Run the PostgreSQL-backed frontier recovery demo:

```powershell
$env:DATABASE_URL='postgresql+asyncpg://atlaspipe:atlaspipe@localhost:55432/atlaspipe'
.\.venv\Scripts\python scripts\postgres_frontier_recovery_demo.py
```

Run the real worker-death demo:

```powershell
$env:DATABASE_URL='postgresql+asyncpg://atlaspipe:atlaspipe@localhost:55432/atlaspipe'
.\.venv\Scripts\python scripts\postgres_worker_death_demo.py --records 100000 --workers 8 --worker-concurrency 50 --batch-size 50 --slow-records 400 --slow-delay-seconds 8 --lease-seconds 5 --kill-after-seconds 5 --timeout-seconds 2400 --max-attempts 10
```

## API Examples

```powershell
$env:API_KEY=(Get-Content .env | Where-Object { $_ -match '^API_KEY=' }) -replace '^API_KEY=',''
$headers=@{Authorization="Bearer $env:API_KEY"}
Invoke-RestMethod http://localhost:8000/live
Invoke-RestMethod http://localhost:8000/ready
$body=@{urls=@('https://example.com')} | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/crawl -Method Post -Headers $headers -ContentType 'application/json' -Body $body
Invoke-RestMethod 'http://localhost:8000/pages?limit=25&domain=example.com' -Headers $headers
Invoke-RestMethod http://localhost:8000/stats -Headers $headers
```

## Benchmarks

Benchmarks are stored as machine-readable artifacts under `benchmarks/results/`.

High-volume PostgreSQL retest on PostgreSQL 16.15:

| Test | Result |
|---|---:|
| `pages` rows after run | 1,822,000 |
| Database size after run | 2,273 MB |
| 1,000,000-row COPY load | 60.274731 s |
| 1,000,000-row COPY throughput | 16,590.70 records/sec |
| normalized URL lookup avg | 1.833 ms |
| domain + recent filter avg | 0.965 ms |
| status-code filter avg | 0.546 ms |
| domain aggregate rollup avg | 1.086 ms |

High-concurrency `pgbench` retest:

| Test | Result |
|---|---:|
| Scale factor | 50 |
| Clients | 100 |
| Threads | 8 |
| Duration | 60 s |
| Transactions processed | 263,913 |
| Failed transactions | 0 |
| TPS | 4,484.83 |
| Average latency | 22.223 ms |

Controlled full-pipeline fixture benchmark:

| Test | Result |
|---|---:|
| Largest fixture run | 100,000 pages |
| Concurrency tested | 1 / 5 / 10 / 25 / 50 |
| Best 100k throughput | 1,277.78 records/sec |
| 100k p95 latency at best throughput | 353.450 ms |
| Failures | 0 |

PostgreSQL frontier recovery demo:

| Test | Result |
|---|---:|
| Scheduled records | 10,000 |
| SQL-backed workers | 4 |
| Leases abandoned by simulated crashed worker | 500 |
| Expired leases recovered through PostgreSQL | 500 |
| Completed records | 10,000 |
| Stale completions rejected by lease fencing | 1 |
| Logical pages persisted | 10,000 |
| Lost records | 0 |

Real worker-death experiment:

| Test | Result |
|---|---:|
| Scheduled records | 100,000 |
| Independent worker processes | 8 |
| Worker processes killed | 1 |
| Leases orphaned by killed worker | 50 |
| Leases recovered by surviving workers | 50 |
| Completed records | 100,000 |
| Dead / pending / leased records at finish | 0 / 0 / 0 |
| Logical pages persisted | 100,000 |
| Logical duplicate pages | 0 |
| Lost records | 0 |
| Throughput | 71.21 pages/sec |

Raw result: `benchmarks/results/postgres_worker_death_demo.json`.

See [docs/BENCHMARKS.md](docs/BENCHMARKS.md) for methodology, raw-result file names, and
query-plan notes.

For the system-design narrative, see
[docs/ENGINEERING_REPORT.md](docs/ENGINEERING_REPORT.md).

## Testing Coverage

The deterministic test suite covers:

- URL normalization
- HTML metadata extraction
- malformed HTML handling
- link classification
- hashing and deduplication
- durable frontier scheduling, lease recovery, and retry exhaustion
- lease renewal for long-lived worker operations
- retry classification, `Retry-After`, and transient HTTP status handling
- domain concurrency limiting
- URL safety validation, including private-address rejection
- PostgreSQL frontier fencing integration when `DATABASE_URL` is configured
- API health, crawl job, page, domain, and stats endpoints
- fixture-driven end-to-end pipeline behavior

Latest local verification:

```text
31 tests passed, 1 PostgreSQL integration test skipped without DATABASE_URL
PostgreSQL integration test passed locally with DATABASE_URL
ruff passed
ruff format --check passed
mypy passed
```

## Engineering Trade-offs

- The durable frontier uses at-least-once delivery with idempotent page writes. AtlasPipe
  does not claim exactly-once execution.
- Workers enforce global RPS and per-domain concurrency limits, retry transient HTTP
  statuses with backoff, and revalidate DNS-resolved URLs and redirects before fetching.
- Exact hash and URL deduplication are cheap and deterministic; near-duplicate comparison
  is optional because it is more expensive and subjective.
- PostgreSQL is a good fit for URL lookup, domain filtering, job accounting, attempts,
  and aggregate queries.
- High-volume ingest uses `COPY`-style loading because single-row inserts are not the
  right path for bulk data.

## Limits And Next Steps

- Robots.txt fetching is represented by a cache boundary but would need production-grade
  fetching and caching before broader crawling.
- `/crawl` creates a job and schedules URLs into the durable frontier. Docker Compose now
  runs a separate worker process; production deployment would still need a real
  supervisor and multiple worker replicas.
- CI runs PostgreSQL 16 and applies Alembic migrations before the test suite.
- Domain aggregates became expensive at million-row scale; AtlasPipe now includes a
  measured `domain_stats` rollup path. A production system would need a freshness policy.
- Docker Compose assets are included, but the high-volume benchmark was run against a
  local PostgreSQL 16.15 runtime on Windows rather than inside Docker.
