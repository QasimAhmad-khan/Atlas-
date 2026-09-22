"""add durable crawl frontier

Revision ID: 20260922_0002
Revises: 20260922_0001
Create Date: 2026-09-22 22:15:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260922_0002"
down_revision: str | None = "20260922_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crawl_frontier",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("state", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_type", sa.String(length=128), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["crawl_jobs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("job_id", "normalized_url", name="uq_crawl_frontier_job_url"),
        sa.CheckConstraint(
            "state IN ('pending', 'leased', 'complete', 'failed', 'dead')",
            name="ck_crawl_frontier_state",
        ),
        sa.CheckConstraint("priority >= 0", name="ck_crawl_frontier_priority_nonnegative"),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_crawl_frontier_attempt_count_nonnegative"
        ),
        sa.CheckConstraint("max_attempts >= 1", name="ck_crawl_frontier_max_attempts_positive"),
    )
    op.create_index(
        "ix_crawl_frontier_claimable",
        "crawl_frontier",
        ["state", "available_at", "priority", "created_at"],
    )
    op.create_index(
        "ix_crawl_frontier_domain_state_available",
        "crawl_frontier",
        ["domain", "state", "available_at"],
    )
    op.create_index("ix_crawl_frontier_job_state", "crawl_frontier", ["job_id", "state"])
    op.create_index(
        "ix_crawl_frontier_lease_expires_at",
        "crawl_frontier",
        ["lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_crawl_frontier_lease_expires_at", table_name="crawl_frontier")
    op.drop_index("ix_crawl_frontier_job_state", table_name="crawl_frontier")
    op.drop_index("ix_crawl_frontier_domain_state_available", table_name="crawl_frontier")
    op.drop_index("ix_crawl_frontier_claimable", table_name="crawl_frontier")
    op.drop_table("crawl_frontier")
