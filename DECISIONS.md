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
