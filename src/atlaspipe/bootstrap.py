"""One-off, admin-only bootstrap for the least-privilege RDS IAM application role."""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from atlaspipe.db.session import create_engine


async def bootstrap() -> None:
    engine = create_engine()
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("""
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'atlaspipe_app') THEN
                        CREATE ROLE atlaspipe_app LOGIN;
                    END IF;
                END $$;
            """)
            )
            for statement in (
                "GRANT rds_iam TO atlaspipe_app",
                "GRANT USAGE ON SCHEMA public TO atlaspipe_app",
                "GRANT SELECT, INSERT, UPDATE, DELETE ON crawl_jobs, crawl_frontier, pages, "
                "crawl_attempts, links, domain_stats, api_quotas, worker_heartbeats "
                "TO atlaspipe_app",
                "GRANT SELECT ON alembic_version TO atlaspipe_app",
                "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO atlaspipe_app",
            ):
                await connection.execute(text(statement))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(bootstrap())
