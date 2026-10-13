from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request
from sqlalchemy import delete, func
from sqlalchemy.dialects.postgresql import insert

from atlaspipe.config import Settings
from atlaspipe.db.models import ApiQuota


def authorize_write(request: Request) -> None:
    settings: Settings = request.app.state.settings
    write_key = settings.api_key.get_secret_value()
    if not write_key:
        raise HTTPException(503, "job submission is not configured")
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            401, "bearer credential required", headers={"WWW-Authenticate": "Bearer"}
        )
    if not hmac.compare_digest(token.encode(), write_key.encode()):
        read_key = settings.api_read_key.get_secret_value()
        if read_key and hmac.compare_digest(token.encode(), read_key.encode()):
            raise HTTPException(403, "credential does not allow job submission")
        raise HTTPException(401, "invalid credential", headers={"WWW-Authenticate": "Bearer"})
    request.state.principal = hashlib.sha256(token.encode()).hexdigest()


async def consume_quota(request: Request, url_count: int) -> None:
    settings: Settings = request.app.state.settings
    if url_count > settings.api_urls_per_minute:
        raise HTTPException(429, "URL quota exceeded", headers={"Retry-After": "60"})
    if getattr(request.app.state, "repository", None) is not None:
        # shortcut: injected repositories are test-only; deployed apps always use PostgreSQL.
        now = int(datetime.now(UTC).timestamp()) // 60
        async with request.app.state.quota_lock:
            requests, urls = request.app.state.test_quota.get(now, (0, 0))
            allowed = (
                requests < settings.api_requests_per_minute
                and urls + url_count <= settings.api_urls_per_minute
            )
            if allowed:
                request.app.state.test_quota = {now: (requests + 1, urls + url_count)}
    else:
        async with request.app.state.engine.begin() as connection:
            # Use the database clock so independent API replicas share the same window.
            window = func.date_trunc("minute", func.now())
            statement = insert(ApiQuota).values(
                principal=request.state.principal, window=window, requests=1, urls=url_count
            )
            result = await connection.execute(
                statement.on_conflict_do_update(
                    index_elements=[ApiQuota.principal, ApiQuota.window],
                    set_={"requests": ApiQuota.requests + 1, "urls": ApiQuota.urls + url_count},
                    where=(ApiQuota.requests < settings.api_requests_per_minute)
                    & (ApiQuota.urls + url_count <= settings.api_urls_per_minute),
                ).returning(ApiQuota.requests)
            )
            allowed = result.scalar_one_or_none() is not None
            await connection.execute(
                delete(ApiQuota).where(ApiQuota.window < func.now() - timedelta(minutes=5))
            )
    if not allowed:
        raise HTTPException(429, "submission quota exceeded", headers={"Retry-After": "60"})
