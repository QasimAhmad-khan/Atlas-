from __future__ import annotations

import random
from dataclasses import dataclass

TRANSIENT_HTTP_STATUSES = {429, 500, 502, 503, 504}


def should_retry_status(status: int | None) -> bool:
    return status in TRANSIENT_HTTP_STATUSES


def should_retry_error(error: BaseException) -> bool:
    return isinstance(error, (TimeoutError, ConnectionError, OSError))


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 5.0
    jitter_seconds: float = 0.1

    def delay_for_attempt(self, attempt_number: int) -> float:
        exponential = self.base_delay_seconds * (2 ** max(attempt_number - 1, 0))
        jitter = self.jitter_seconds * random.random()  # noqa: S311
        return float(min(exponential + jitter, self.max_delay_seconds))
