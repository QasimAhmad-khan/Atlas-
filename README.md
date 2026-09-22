# AtlasPipe

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

## Why This Project

MixRank describes its product as a data platform for company, people, job, app, and
technographic data, refreshed frequently and delivered through APIs, warehouse tables,
PostgreSQL, and flat files. AtlasPipe focuses on the lower-level engineering skills behind
that style of system:

- bounded async ingestion
- URL and domain normalization
- content hashing and deduplication
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
Scheduler
 |
 v
Bounded Queue
 |
 +-- Worker
 +-- Worker
 +-- Worker
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
Batch Writer
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
  crawler/          aiohttp fetcher, retry policy, rate limiting
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

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[dev]"
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
docker compose up --build
```

The compose stack starts PostgreSQL and the API, applies Alembic migrations on app
startup, and exposes FastAPI on `http://localhost:8000`.

Apply migrations manually:

```powershell
.\.venv\Scripts\python -m alembic upgrade head
```

## API Examples

```powershell
curl http://localhost:8000/health
curl -X POST http://localhost:8000/crawl -H "Content-Type: application/json" -d "{\"urls\":[\"https://example.com\"]}"
curl "http://localhost:8000/pages?limit=25&domain=example.com"
curl http://localhost:8000/stats
curl http://localhost:8000/stats/domains
curl http://localhost:8000/stats/status-codes
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

See [docs/BENCHMARKS.md](docs/BENCHMARKS.md) for methodology, raw-result file names, and
query-plan notes.

## Testing Coverage

The deterministic test suite covers:

- URL normalization
- HTML metadata extraction
- malformed HTML handling
- link classification
- hashing and deduplication
- retry classification
- domain concurrency limiting
- URL safety validation
- API health, crawl job, page, domain, and stats endpoints
- fixture-driven end-to-end pipeline behavior

Latest local verification:

```text
21 tests passed
ruff passed
ruff format --check passed
mypy passed
```

## Engineering Trade-offs

- A single service keeps the project reviewable, while internal package boundaries leave
  room for queue-backed workers later.
- Exact hash and URL deduplication are cheap and deterministic; near-duplicate comparison
  is optional because it is more expensive and subjective.
- PostgreSQL is a good fit for URL lookup, domain filtering, job accounting, attempts,
  and aggregate queries.
- High-volume ingest uses `COPY`-style loading because single-row inserts are not the
  right path for bulk data.

## Limits And Next Steps

- Robots.txt fetching is represented by a cache boundary but would need production-grade
  fetching and caching before broader crawling.
- `/crawl` currently creates jobs through the API boundary; a production version should
  move execution to durable background workers.
- Domain aggregates become expensive at million-row scale and would benefit from rollup
  tables or materialized views.
- Docker Compose assets are included, but the high-volume benchmark was run against a
  local PostgreSQL 16.15 runtime on Windows rather than inside Docker.
