from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import HTTPException, Request

from atlaspipe.config import Settings, get_settings
from atlaspipe.db.repositories import PageRepository, SqlAlchemyRepository


def settings_dependency() -> Settings:
    return get_settings()


async def repository_dependency(request: Request) -> AsyncIterator[PageRepository]:
    repository = getattr(request.app.state, "repository", None)
    if repository is not None:
        yield repository
        return

    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise HTTPException(status_code=503, detail="database is not configured")

    async with session_factory() as session:
        try:
            yield SqlAlchemyRepository(session)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
