"""add domain stats rollup

Revision ID: 20260922_0003
Revises: 20260922_0002
Create Date: 2026-09-22 22:45:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260922_0003"
down_revision: str | None = "20260922_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "domain_stats",
        sa.Column("domain", sa.String(length=255), primary_key=True),
        sa.Column("page_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("success_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("failure_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("total_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("unique_content_hashes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("last_crawled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("page_count >= 0", name="ck_domain_stats_page_count_nonnegative"),
        sa.CheckConstraint("success_count >= 0", name="ck_domain_stats_success_count_nonnegative"),
        sa.CheckConstraint("failure_count >= 0", name="ck_domain_stats_failure_count_nonnegative"),
        sa.CheckConstraint("total_bytes >= 0", name="ck_domain_stats_total_bytes_nonnegative"),
        sa.CheckConstraint(
            "unique_content_hashes >= 0",
            name="ck_domain_stats_unique_content_hashes_nonnegative",
        ),
    )
    op.create_index("ix_domain_stats_page_count", "domain_stats", ["page_count"])
    op.create_index("ix_domain_stats_last_crawled_at", "domain_stats", ["last_crawled_at"])


def downgrade() -> None:
    op.drop_index("ix_domain_stats_last_crawled_at", table_name="domain_stats")
    op.drop_index("ix_domain_stats_page_count", table_name="domain_stats")
    op.drop_table("domain_stats")
