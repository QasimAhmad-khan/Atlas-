from __future__ import annotations

import socket
from unittest.mock import AsyncMock

import aiohttp
import pytest
from aiohttp.abc import ResolveResult

from atlaspipe.crawler.fetcher import PublicResolver, UnsafeUrlError
from atlaspipe.pipeline.validation import validate_public_url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1",
        "http://[::1]",
        "http://169.254.169.254",
        "http://localhost.",
        "http://u:p@example.com",
    ],
)
def test_unsafe_url_forms(url: str) -> None:
    assert not validate_public_url(url).is_valid


async def test_connector_rejects_dns_rebinding(monkeypatch: pytest.MonkeyPatch) -> None:
    answer: ResolveResult = {
        "hostname": "public.example",
        "host": "127.0.0.1",
        "port": 80,
        "family": socket.AF_INET,
        "proto": 0,
        "flags": 0,
    }
    monkeypatch.setattr(aiohttp.ThreadedResolver, "resolve", AsyncMock(return_value=[answer]))
    resolver = PublicResolver()
    with pytest.raises(UnsafeUrlError, match="non_public"):
        await resolver.resolve("public.example", 80)
    await resolver.close()
