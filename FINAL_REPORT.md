# Final Engineering Report

## Project Summary

AtlasPipe is an asynchronous Python ingestion pipeline for permitted public web resources.
It normalizes and deduplicates page records, stores structured data through a repository
boundary designed for PostgreSQL, and exposes query endpoints through FastAPI.

## Technology Stack

Python 3.12+, asyncio, aiohttp, FastAPI, Pydantic, SQLAlchemy 2.x, Alembic, asyncpg,
PostgreSQL, pytest, Ruff, mypy, Docker, and Docker Compose.

## Testing Summary

The local deterministic test suite contains 21 tests covering API behavior, pipeline
fixtures, metadata schema checks, URL normalization, parsing, link classification,
deduplication, retry logic, rate limiting, and URL safety validation.

## Benchmark Summary

Synthetic ingestion benchmark: best measured local run was 1,324.12 records/sec for 100
records at concurrency 5. In-memory insert benchmark: 10,000 records improved from
2,028.13 records/sec single-row writes to 87,401.05 records/sec with batch size 100.

## Failure Scenarios Tested

Malformed HTML, duplicate URL/content records, 404 retry classification, transient retry
classification, localhost/private/link-local/metadata URL blocking, and bounded
per-domain concurrency.

## Security Decisions

The crawler rejects localhost, loopback, private, link-local, reserved, unspecified, and
cloud metadata IP targets by default. It parses HTML but does not execute JavaScript or
remote content.

## Known Limitations

Live PostgreSQL migration, Docker Compose startup, and EXPLAIN ANALYZE verification could
not be run because Docker, PostgreSQL, and `psql` are not installed or reachable in this
environment.

## Strongest Engineering Aspects

- Clear package boundaries for crawling, parsing, pipeline, persistence, API, and metrics.
- Bounded async worker pipeline with rate and domain concurrency controls.
- Intentional PostgreSQL schema with constraints and indexes.
- Deterministic tests across core transformation and API behavior.
- Honest benchmark artifacts generated from executed scripts.

## Improvements With More Time

- Run and tune live PostgreSQL benchmarks and EXPLAIN ANALYZE plans.
- Add a real durable background worker for `/crawl` jobs.
- Add Prometheus/OpenTelemetry and richer failure-attempt persistence.
