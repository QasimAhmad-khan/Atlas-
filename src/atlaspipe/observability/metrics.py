from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, median


@dataclass
class Metrics:
    requests_attempted: int = 0
    requests_succeeded: int = 0
    requests_failed: int = 0
    retry_count: int = 0
    pages_processed: int = 0
    deduplicated_records: int = 0
    response_latencies_ms: list[int] = field(default_factory=list)
    database_batch_timings_ms: list[int] = field(default_factory=list)

    def snapshot(self) -> dict[str, float | int]:
        sorted_latencies = sorted(self.response_latencies_ms)
        p50 = median(sorted_latencies) if sorted_latencies else 0
        p95 = sorted_latencies[int(len(sorted_latencies) * 0.95) - 1] if sorted_latencies else 0
        return {
            "requests_attempted": self.requests_attempted,
            "requests_succeeded": self.requests_succeeded,
            "requests_failed": self.requests_failed,
            "retry_count": self.retry_count,
            "pages_processed": self.pages_processed,
            "average_response_time_ms": mean(sorted_latencies) if sorted_latencies else 0,
            "p50_latency_ms": p50,
            "p95_latency_ms": p95,
            "deduplicated_records": self.deduplicated_records,
            "average_database_batch_ms": mean(self.database_batch_timings_ms)
            if self.database_batch_timings_ms
            else 0,
        }
