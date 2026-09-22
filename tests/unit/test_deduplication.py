from __future__ import annotations

from atlaspipe.pipeline.deduplication import Deduplicator, sha256_hexdigest, token_similarity


def test_hashing_is_deterministic() -> None:
    assert sha256_hexdigest("same") == sha256_hexdigest("same")
    assert sha256_hexdigest("same") != sha256_hexdigest("different")


def test_deduplicator_detects_url_and_content_duplicates() -> None:
    deduplicator = Deduplicator()
    first = deduplicator.check_and_remember(
        normalized_url="https://example.com/",
        content_hash="abc",
        text="hello world",
    )
    second = deduplicator.check_and_remember(
        normalized_url="https://example.com/",
        content_hash="abc",
        text="hello world",
    )

    assert not first.normalized_url_seen
    assert second.normalized_url_seen
    assert second.content_hash_seen


def test_token_similarity_is_explainable() -> None:
    assert token_similarity("alpha beta", "alpha beta gamma") > 0.5
