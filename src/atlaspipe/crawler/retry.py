from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

TRANSIENT_HTTP_STATUSES = {429, 500, 502, 503, 504}


def should_retry_status(status: int | None) -> bool:
    return status in TRANSIENT_HTTP_STATUSES


def should_retry_error(error: BaseException) -> bool:
    return isinstance(error, (TimeoutError, ConnectionError, OSError))


def retry_after_seconds(value: str | None) -> int | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return max(int(stripped), 0)
    except ValueError:
        pass

    try:
        parsed = parsedate_to_datetime(stripped)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return max(int((parsed - datetime.now(UTC)).total_seconds()), 0)


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
