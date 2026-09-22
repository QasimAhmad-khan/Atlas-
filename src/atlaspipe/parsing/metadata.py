from __future__ import annotations

import re

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})\b", re.IGNORECASE)


def detect_email_domains(text: str) -> list[str]:
    return sorted({match.group(1).lower() for match in EMAIL_RE.finditer(text)})


def detect_technology_hints(html: str, headers: dict[str, str] | None = None) -> list[str]:
    lowered = html.lower()
    hints: set[str] = set()
    headers = {key.lower(): value.lower() for key, value in (headers or {}).items()}

    if "wp-content" in lowered or "wordpress" in lowered:
        hints.add("wordpress")
    if "cdn.shopify.com" in lowered or "shopify" in lowered:
        hints.add("shopify")
    if "react" in lowered or "data-reactroot" in lowered:
        hints.add("react")
    if "next/static" in lowered or "__next" in lowered:
        hints.add("nextjs")
    if "x-powered-by" in headers:
        hints.add(f"x-powered-by:{headers['x-powered-by']}")
    if "server" in headers:
        hints.add(f"server:{headers['server']}")

    return sorted(hints)


def normalize_whitespace(text: str) -> str:
    return " ".join(text.split())
