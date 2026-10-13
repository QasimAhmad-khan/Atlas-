"""Carry W3C trace context across the durable queue (expand only)."""

import sqlalchemy as sa
from alembic import op

revision = "20261014_0006"
down_revision = "20261014_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crawl_jobs", sa.Column("traceparent", sa.String(55), nullable=True))


def downgrade() -> None:
    op.drop_column("crawl_jobs", "traceparent")
