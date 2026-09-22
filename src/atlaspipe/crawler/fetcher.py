from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urljoin

import aiohttp

from atlaspipe.pipeline.validation import validate_resolved_public_url


@dataclass(frozen=True)
class FetchResult:
    url: str
    final_url: str
    status: int | None
    headers: dict[str, str]
    body: bytes
    response_time_ms: int
    error_type: str | None = None
    error_message: str | None = None

    @property
    def content_type(self) -> str | None:
        return self.headers.get("content-type")


class ResponseTooLargeError(Exception):
    pass


class UnsafeUrlError(Exception):
    pass


class TooManyRedirectsError(Exception):
    pass


class AioHttpFetcher:
    def __init__(
        self,
        *,
        timeout_seconds: float,
        user_agent: str,
        max_response_bytes: int,
        max_redirects: int = 10,
    ) -> None:
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._user_agent = user_agent
        self._max_response_bytes = max_response_bytes
        self._max_redirects = max_redirects
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> AioHttpFetcher:
        self._session = aiohttp.ClientSession(
            timeout=self._timeout,
            headers={"User-Agent": self._user_agent},
            raise_for_status=False,
        )
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        if self._session is not None:
            await self._session.close()

    async def fetch(self, url: str) -> FetchResult:
        if self._session is None:
            raise RuntimeError("AioHttpFetcher must be used as an async context manager")

        started = time.perf_counter()
        try:
            current_url = url
            validation = await validate_resolved_public_url(current_url)
            if not validation.is_valid:
                raise UnsafeUrlError(validation.reason or "unsafe_url")

            for _redirect in range(self._max_redirects + 1):
                async with self._session.get(current_url, allow_redirects=False) as response:
                    headers = {key.lower(): value for key, value in response.headers.items()}
                    if response.status in {301, 302, 303, 307, 308} and "location" in headers:
                        current_url = urljoin(str(response.url), headers["location"])
                        validation = await validate_resolved_public_url(current_url)
                        if not validation.is_valid:
                            raise UnsafeUrlError(validation.reason or "unsafe_redirect_url")
                        continue

                    body = await self._read_limited(response)
                    elapsed_ms = int((time.perf_counter() - started) * 1000)
                    return FetchResult(
                        url=url,
                        final_url=str(response.url),
                        status=response.status,
                        headers=headers,
                        body=body,
                        response_time_ms=elapsed_ms,
                    )
            raise TooManyRedirectsError(f"exceeded {self._max_redirects} redirects")
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return FetchResult(
                url=url,
                final_url=url,
                status=None,
                headers={},
                body=b"",
                response_time_ms=elapsed_ms,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

    async def _read_limited(self, response: aiohttp.ClientResponse) -> bytes:
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.content.iter_chunked(64 * 1024):
            total += len(chunk)
            if total > self._max_response_bytes:
                raise ResponseTooLargeError(f"response exceeded {self._max_response_bytes} bytes")
            chunks.append(chunk)
        return b"".join(chunks)
