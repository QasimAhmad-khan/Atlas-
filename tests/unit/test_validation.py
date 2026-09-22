from __future__ import annotations

from atlaspipe.pipeline.validation import validate_public_url


def test_validate_public_url_blocks_localhost_and_private_ranges() -> None:
    assert not validate_public_url("http://localhost:8000").is_valid
    assert not validate_public_url("http://127.0.0.1").is_valid
    assert not validate_public_url("http://10.0.0.5").is_valid
    assert not validate_public_url("http://169.254.169.254/latest/meta-data").is_valid


def test_validate_public_url_accepts_public_urls() -> None:
    assert validate_public_url("https://example.com/path").is_valid
