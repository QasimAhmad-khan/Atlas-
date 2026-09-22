# AtlasPipe

AtlasPipe is an asynchronous Python data-ingestion pipeline that crawls permitted public
web resources, normalizes and deduplicates records, persists structured data to
PostgreSQL, and exposes indexed querying through FastAPI.

The project explores practical engineering problems that appear in data-heavy backend
systems: bounded concurrency, fault-tolerant ingestion, batch persistence,
deduplication, data modeling, indexing, observability, and performance measurement.

Current status: checkpoint 0 repository bootstrap is in progress. See
`PROJECT_STATUS.md` for the latest verified state.

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
.\.venv\Scripts\python -c "import atlaspipe; print(atlaspipe.__version__)"
```

The complete quick start will be expanded as the database, Docker, pipeline, API, and
benchmark checkpoints are implemented and verified.
