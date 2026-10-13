from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from atlaspipe.config import Settings, get_settings
from atlaspipe.observability.telemetry import instrument_database


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    resolved = settings or get_settings()
    engine = create_async_engine(
        resolved.database_url,
        pool_pre_ping=True,
        pool_size=resolved.database_pool_size,
        max_overflow=resolved.database_max_overflow,
        pool_timeout=resolved.database_pool_timeout,
        connect_args={"command_timeout": resolved.database_command_timeout, "timeout": 5},
    )
    instrument_database(engine)
    return engine


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
