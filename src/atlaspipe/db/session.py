from __future__ import annotations

import ssl
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import event
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
    connect_args: dict[str, Any] = {
        "command_timeout": resolved.database_command_timeout,
        "timeout": 5,
    }
    if resolved.database_ssl:
        connect_args["ssl"] = ssl.create_default_context(cafile=resolved.database_ca_file or None)
    engine = create_async_engine(
        resolved.database_url,
        pool_pre_ping=True,
        pool_size=resolved.database_pool_size,
        max_overflow=resolved.database_max_overflow,
        pool_timeout=resolved.database_pool_timeout,
        connect_args=connect_args,
    )
    instrument_database(engine)
    if resolved.database_auth == "iam":

        @event.listens_for(engine.sync_engine, "do_connect")
        def iam_connect(
            _dialect: object, _connection_record: object, _args: object, params: dict[str, Any]
        ) -> None:
            import boto3  # type: ignore[import-untyped]

            params["password"] = boto3.client(
                "rds", region_name=resolved.aws_region
            ).generate_db_auth_token(
                DBHostname=resolved.db_host,
                Port=resolved.db_port,
                DBUsername=resolved.db_username,
            )

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
