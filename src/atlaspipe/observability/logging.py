from __future__ import annotations

import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import structlog


def redact_secrets(
    _logger: object, _method: str, event: MutableMapping[str, Any]
) -> dict[str, Any]:
    def clean(value: Any, key: str = "") -> Any:
        if any(
            part in key.lower()
            for part in ("password", "token", "secret", "authorization", "api_key")
        ):
            return "[redacted]"
        if isinstance(value, dict):
            return {k: clean(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, str):

            def safe_url(match: re.Match[str]) -> str:
                split = urlsplit(match.group())
                return urlunsplit(
                    (split.scheme, split.netloc.rsplit("@", 1)[-1], split.path, "", "")
                )

            return re.sub(r"[a-z][a-z0-9+.-]*://[^\s\"']+", safe_url, value)
        return value

    return {key: clean(value, key) for key, value in event.items()}


def configure_logging(level: str) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            redact_secrets,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
