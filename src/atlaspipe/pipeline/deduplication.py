from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


def sha256_hexdigest(value: str | bytes) -> str:
    payload = value.encode("utf-8", errors="replace") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def token_similarity(left: str, right: str) -> float:
    left_tokens = {token for token in left.lower().split() if token}
    right_tokens = {token for token in right.lower().split() if token}
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


@dataclass
class DeduplicationResult:
    normalized_url_seen: bool
    content_hash_seen: bool
    near_duplicate: bool = False


@dataclass
class Deduplicator:
    near_duplicate_threshold: float | None = None
    _urls: set[str] = field(default_factory=set)
    _content_hashes: set[str] = field(default_factory=set)
    _texts: list[str] = field(default_factory=list)

    def check_and_remember(
        self,
        *,
        normalized_url: str,
        content_hash: str,
        text: str,
    ) -> DeduplicationResult:
        url_seen = normalized_url in self._urls
        hash_seen = content_hash in self._content_hashes
        near_duplicate = False

        if self.near_duplicate_threshold is not None:
            near_duplicate = any(
                token_similarity(text, existing) >= self.near_duplicate_threshold
                for existing in self._texts
            )

        self._urls.add(normalized_url)
        self._content_hashes.add(content_hash)
        if text:
            self._texts.append(text)

        return DeduplicationResult(
            normalized_url_seen=url_seen,
            content_hash_seen=hash_seen,
            near_duplicate=near_duplicate,
        )
