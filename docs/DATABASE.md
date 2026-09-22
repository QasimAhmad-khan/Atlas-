# Database

The PostgreSQL schema is managed by Alembic.

## Tables

- `crawl_jobs`: job lifecycle, requested URLs, and aggregate counts.
- `pages`: normalized page records with URL uniqueness, content hashes, metadata, and
  latency fields.
- `crawl_attempts`: per-attempt success/failure history.
- `links`: extracted outbound links keyed to a source page.

## Key Constraints

- `pages.normalized_url` is unique for exact URL deduplication.
- Link rows are unique by `(source_page_id, target_url)`.
- Status and count fields have check constraints to reject invalid states.

## Indexes

The migration adds indexes for normalized URL lookup, domain filtering, content hashes,
creation time, crawl job status, HTTP status, source page links, and target domains.

Live `EXPLAIN ANALYZE` runs were executed against PostgreSQL 16.15. At 1.822M `pages`
rows, normalized URL lookup used `ix_pages_normalized_url` directly and completed in
0.039 ms execution time. The domain/recent query returned 100 rows in 0.080 ms execution
time. The broad domain aggregate used a parallel sequential scan and took 723.389 ms,
which points to rollup tables or materialized views as the next optimization.
