from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse


@dataclass(frozen=True)
class ClassifiedLink:
    url: str
    domain: str | None
    is_internal: bool


def extract_domain(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.hostname or "").lower()


def classify_links(base_url: str, hrefs: list[str]) -> list[ClassifiedLink]:
    base_domain = extract_domain(base_url)
    classified: list[ClassifiedLink] = []
    seen: set[str] = set()

    for href in hrefs:
        href = href.strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue

        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue

        target_domain = (parsed.hostname or "").lower() or None
        if absolute in seen:
            continue
        seen.add(absolute)
        classified.append(
            ClassifiedLink(
                url=absolute,
                domain=target_domain,
                is_internal=target_domain == base_domain,
            )
        )

    return classified
