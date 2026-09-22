"""add frontier lease tokens

Revision ID: 20260922_0004
Revises: 20260922_0003
Create Date: 2026-09-22 23:20:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260922_0004"
down_revision: str | None = "20260922_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("crawl_frontier", sa.Column("lease_token", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("crawl_frontier", "lease_token")
