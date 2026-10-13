"""Add shared submission quotas and worker heartbeats (expand only)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261014_0005"
down_revision = "20260922_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_quotas",
        sa.Column("principal", sa.String(64), primary_key=True),
        sa.Column("window", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("requests", sa.Integer(), nullable=False),
        sa.Column("urls", sa.Integer(), nullable=False),
    )
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(128), primary_key=True),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("progress_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("release", sa.String(128), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("worker_heartbeats")
    op.drop_table("api_quotas")
