# Engineering Decisions

## Decision: Use a `src/` Python package layout

Reason: A `src/` layout catches accidental imports from the repository root and makes
test behavior closer to installed-package behavior.

Alternatives considered: A flat package layout at repository root.

Trade-off: The `src/` layout adds a small amount of packaging ceremony, but it improves
import hygiene for a portfolio project that will be tested and run in multiple ways.

## Decision: Start with one FastAPI service and internal pipeline modules

Reason: The brief values a working, well-tested data pipeline over premature distributed
infrastructure. A single service can still preserve clear boundaries between API,
crawler, parsing, persistence, and observability.

Alternatives considered: Separate API and worker services from the first checkpoint.

Trade-off: A single service has simpler deployment and testing. If workload grows, the
same module boundaries can later support a queue-backed worker split.

## Decision: Bind the development API host to localhost by default

Reason: Local development should not expose the API on every network interface unless a
runtime environment explicitly asks for that behavior.

Alternatives considered: Defaulting to `0.0.0.0` for Docker convenience.

Trade-off: Docker configuration will need to override `API_HOST` when containerized, but
the default setting is safer and satisfies static security checks.

## Decision: Use Pydantic Settings for typed environment configuration

Reason: The project relies heavily on environment-specific limits and connection strings.
Pydantic Settings keeps those values typed, validated, and centralized.

Alternatives considered: Direct `os.environ` reads or a hand-written config loader.

Trade-off: This adds one small dependency, but it avoids duplicated parsing logic and
makes invalid configuration fail early.

## Decision: Model relational crawl data in PostgreSQL tables

Reason: The project needs indexed URL lookup, domain filtering, crawl job accounting,
attempt history, and link traversal. Explicit relational tables make those access
patterns visible and testable.

Alternatives considered: Storing each crawled page as a JSON document in one table.

Trade-off: Relational modeling takes more schema design up front, but it produces
clearer constraints, better query plans, and stronger portfolio evidence for SQL and
data modeling.

## Decision: Use normalized URL uniqueness plus content-hash indexing

Reason: URL deduplication and content deduplication are separate concerns. A unique
normalized URL prevents repeated ingestion of the same address, while a content-hash
index supports finding different URLs with identical payloads.

Alternatives considered: Unique content hash only, or no uniqueness constraints until
pipeline-level deduplication.

Trade-off: URL uniqueness is strict and easy to enforce. Content hashes remain indexed
but not unique because distinct pages can legitimately share the same content.
