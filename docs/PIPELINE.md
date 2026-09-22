# Pipeline

The pipeline accepts a list of URLs and pushes them through a bounded `asyncio.Queue`.
Workers validate URL safety, apply global and domain-level rate controls, fetch HTML,
parse metadata, normalize URLs and text, compute hashes, deduplicate records, and send
records to a batch writer.

## Deduplication

Level A is normalized URL deduplication. Level B is exact content-hash deduplication.
Level C is represented by an optional token-similarity helper for explainable near
duplicate comparisons.

## Failure Handling

Invalid URLs, fetch errors, oversized responses, and non-HTML responses are treated as
failed page processing events rather than whole-job crashes. Retry classification is
implemented for transient HTTP statuses and temporary network-style errors.

## Batch Writes

The writer collects records up to `BATCH_SIZE` before persistence. The in-memory benchmark
shows the expected shape: batch writes outperform single-row writes at larger scales.
