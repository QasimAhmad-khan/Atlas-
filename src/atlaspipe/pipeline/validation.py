from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class UrlValidationResult:
    is_valid: bool
    reason: str | None = None


BLOCKED_HOSTS = {"localhost", "metadata.google.internal"}
BLOCKED_IPS = {ipaddress.ip_address("169.254.169.254")}


def validate_public_url(url: str, *, allow_private: bool = False) -> UrlValidationResult:
    split = urlsplit(url.strip())
    if split.scheme.lower() not in {"http", "https"}:
        return UrlValidationResult(False, "unsupported_scheme")
    if not split.hostname:
        return UrlValidationResult(False, "missing_host")

    host = split.hostname.lower()
    if host in BLOCKED_HOSTS:
        return UrlValidationResult(False, "blocked_host")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return UrlValidationResult(True)

    if ip in BLOCKED_IPS:
        return UrlValidationResult(False, "metadata_ip")
    if not allow_private and (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return UrlValidationResult(False, "non_public_ip")

    return UrlValidationResult(True)
