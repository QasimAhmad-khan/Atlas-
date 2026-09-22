# Project Status

## Current checkpoint

Whole-project build substantially implemented. Live PostgreSQL verification completed
with a portable PostgreSQL 16.15 runtime. Docker verification remains blocked because
Docker is not installed.

## Completed work

- Created `atlaspipe/` project directory.
- Initialized Git repository.
- Created base source, test, benchmark, script, docs, and CI directories.
- Added initial Python package metadata and dependency configuration.
- Added `.gitignore` and `.env.example`.
- Added initial FastAPI application factory and package entrypoint.
- Created local virtual environment at `.venv/`.
- Installed runtime and development dependencies with `pip install -e ".[dev]"`.
- Verified the package imports and the FastAPI app factory creates an application.
- Added initial smoke tests.
- Implemented SQLAlchemy database models for `crawl_jobs`, `pages`, `crawl_attempts`,
  and `links`.
- Added async SQLAlchemy engine/session factory setup.
- Configured Alembic with an initial PostgreSQL migration.
- Verified Alembic can discover the migration head and generate offline PostgreSQL DDL.
- Implemented URL normalization, HTML parsing, metadata extraction, link classification,
  hashing, deduplication, retry classification, rate limiting, URL safety validation,
  bounded pipeline processing, API routes, metrics, Docker assets, fixture scripts, and
  benchmark tooling.
- Executed deterministic local benchmarks and recorded JSON results.
- Refreshed the completed project into `C:\atlas`.
- Installed portable PostgreSQL 16.15 under `C:\atlas\.postgres_runtime`.
- Started PostgreSQL on `localhost:55432`, created AtlasPipe databases, and applied
  Alembic migrations successfully.
- Executed live PostgreSQL insert/query/EXPLAIN stress benchmark and `pgbench`.

## Checkpoint 0 acceptance

- [x] project directory exists
- [x] git initialized
- [x] Python environment works
- [x] dependencies install successfully
- [x] minimal application imports successfully
- [x] `.gitignore` exists
- [x] `.env.example` exists
- [x] `PROJECT_STATUS.md` exists
- [x] `DECISIONS.md` exists

## Tests executed

- `python -c "import atlaspipe; from atlaspipe.api.app import create_app; app = create_app(); print(atlaspipe.__version__, app.title)"`
- `python -m pytest`
- `python -m ruff check . --no-cache`
- `python -m ruff format --check . --no-cache`
- `python -m mypy`
- `python -m alembic heads`
- `python -m alembic upgrade head --sql`
- `python -m alembic upgrade head`
- `python benchmarks/ingestion_benchmark.py`
- `python benchmarks/database_benchmark.py`
- `python benchmarks/postgres_stress_benchmark.py`
- `pgbench -h localhost -p 55432 -U atlaspipe -i -s 5 atlaspipe`
- `pgbench -h localhost -p 55432 -U atlaspipe -c 20 -j 4 -T 30 -P 10 atlaspipe`

## Test result

- Import smoke test passed: `0.1.0 AtlasPipe`.
- Pytest passed: 2 tests passed.
- Ruff lint passed.
- Ruff format check passed: 25 files already formatted.
- Mypy passed: no issues found in 16 source files.
- Latest pytest passed: 21 tests passed.
- Latest Ruff lint passed.
- Latest Ruff format check passed: 32 files already formatted.
- Latest mypy passed: no issues found in 20 source files.
- Alembic head discovered: `20260922_0001`.
- Offline migration SQL generation passed and produced PostgreSQL DDL for expected
  tables, constraints, and indexes.
- Online migration passed against PostgreSQL 16.15 on `localhost:55432`.
- Ingestion benchmark completed for 100 and 1,000 record scales.
- Database-style in-memory benchmark completed for 100, 1,000, and 10,000 record scales.
- Live PostgreSQL stress inserted 122,000 total `pages` rows.
- `pgbench` processed 138,091 transactions in 30 seconds with zero failed transactions
  and 4,664.980543 TPS.

## Checkpoint 1 acceptance

- [ ] PostgreSQL starts - blocked; Docker/PostgreSQL tools are unavailable.
- [ ] application connects - blocked; no PostgreSQL server is listening on `localhost:5432`.
- [ ] migrations apply from empty database - blocked by missing live PostgreSQL.
- [x] expected tables exist in SQLAlchemy metadata and generated migration SQL.
- [x] expected constraints exist in SQLAlchemy metadata and generated migration SQL.
- [x] expected indexes exist in SQLAlchemy metadata and generated migration SQL.
- [x] migration downgrade/upgrade behavior is reasonable by migration definition and
  offline SQL generation.
- [ ] database tests pass against PostgreSQL - blocked by missing live PostgreSQL.

## Known issues

- Docker is not currently available on PATH in this environment.
- Docker Compose is not currently available on PATH in this environment.
- `psql` is not currently available on PATH in this environment.
- `postgres`, `pg_ctl`, and `pg_isready` are not currently available on PATH.
- `localhost:5432` is not accepting TCP connections.
- Python 3.13.5 is available and satisfies the project requirement of Python 3.12+.
- `py -3.12` is not available, so the project virtual environment will use `python`.

## Next action

Install/start Docker Desktop or a local PostgreSQL server, then rerun
`python -m alembic upgrade head` from the project virtual environment to complete
Checkpoint 1 live database validation.
