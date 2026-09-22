from __future__ import annotations

from atlaspipe.pipeline.normalization import normalize_url


def test_normalize_url_lowercases_scheme_and_host_removes_fragment_and_tracking() -> None:
    assert (
        normalize_url("HTTPS://Example.COM:443/path/?b=2&utm_source=x&a=1#section")
        == "https://example.com/path?a=1&b=2"
    )


def test_normalize_url_preserves_non_default_port() -> None:
    assert normalize_url("http://example.com:8080") == "http://example.com:8080/"
