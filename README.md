# AtlasPipe

AtlasPipe is an asynchronous Python data-ingestion pipeline that crawls permitted public
web resources, normalizes and deduplicates records, persists structured data to
PostgreSQL, and exposes indexed querying through FastAPI.

The project explores practical engineering problems that appear in data-heavy backend
systems: bounded concurrency, fault-tolerant ingestion, batch persistence,
deduplication, data modeling, indexing, observability, and performance measurement.

The implementation includes a bounded async pipeline, HTML parsing, URL normalization,
deduplication, URL safety checks, PostgreSQL schema migrations, FastAPI query endpoints,
Docker assets, tests, and reproducible local benchmarks.

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

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest
```

## Docker Quick Start

```powershell
docker compose up --build
```

The compose stack starts PostgreSQL and the API, applies Alembic migrations on app
startup, and exposes FastAPI on `http://localhost:8000`.

## API Examples

```powershell
curl http://localhost:8000/health
curl -X POST http://localhost:8000/crawl -H "Content-Type: application/json" -d "{\"urls\":[\"https://example.com\"]}"
curl "http://localhost:8000/pages?limit=25&domain=example.com"
curl http://localhost:8000/stats
curl http://localhost:8000/stats/domains
curl http://localhost:8000/stats/status-codes
```

## Verified Commands In This Environment

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check . --no-cache
.\.venv\Scripts\python -m ruff format --check . --no-cache
.\.venv\Scripts\python -m mypy
.\.venv\Scripts\python benchmarks\ingestion_benchmark.py
.\.venv\Scripts\python benchmarks\database_benchmark.py
```

## Current Local Limitations

Docker, Docker Compose, `psql`, and a live PostgreSQL server were not available on this
machine during verification, so live database migration and compose startup could not be
executed here. The PostgreSQL migration was validated through Alembic offline SQL
generation, and the deterministic test suite uses in-memory fixtures for API and pipeline
behavior.
