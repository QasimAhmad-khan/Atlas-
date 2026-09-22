"""initial schema

Revision ID: 20260922_0001
Revises:
Create Date: 2026-09-22 14:45:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260922_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crawl_jobs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_urls", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("processed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("success_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failure_count", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint(
            "status IN ("
            "'pending', 'running', 'completed', 'completed_with_errors', "
            "'failed', 'cancelled'"
            ")",
            name="ck_crawl_jobs_status",
        ),
        sa.CheckConstraint(
            "processed_count >= 0", name="ck_crawl_jobs_processed_count_nonnegative"
        ),
        sa.CheckConstraint("success_count >= 0", name="ck_crawl_jobs_success_count_nonnegative"),
        sa.CheckConstraint("failure_count >= 0", name="ck_crawl_jobs_failure_count_nonnegative"),
    )
    op.create_index("ix_crawl_jobs_created_at", "crawl_jobs", ["created_at"])
    op.create_index("ix_crawl_jobs_status", "crawl_jobs", ["status"])

    op.create_table(
        "pages",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("content_length", sa.BigInteger(), nullable=True),
        sa.Column("html_hash", sa.String(length=64), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("internal_link_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("external_link_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("outbound_link_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("normalized_url", name="uq_pages_normalized_url"),
        sa.CheckConstraint(
            "http_status IS NULL OR http_status BETWEEN 100 AND 599", name="ck_pages_http_status"
        ),
        sa.CheckConstraint(
            "content_length IS NULL OR content_length >= 0",
            name="ck_pages_content_length_nonnegative",
        ),
        sa.CheckConstraint(
            "internal_link_count >= 0", name="ck_pages_internal_link_count_nonnegative"
        ),
        sa.CheckConstraint(
            "external_link_count >= 0", name="ck_pages_external_link_count_nonnegative"
        ),
        sa.CheckConstraint(
            "outbound_link_count >= 0", name="ck_pages_outbound_link_count_nonnegative"
        ),
        sa.CheckConstraint(
            "response_time_ms IS NULL OR response_time_ms >= 0",
            name="ck_pages_response_time_nonnegative",
        ),
    )
    op.create_index("ix_pages_content_hash", "pages", ["content_hash"])
    op.create_index("ix_pages_created_at", "pages", ["created_at"])
    op.create_index("ix_pages_domain", "pages", ["domain"])
    op.create_index("ix_pages_domain_created_at", "pages", ["domain", "created_at"])
    op.create_index("ix_pages_http_status", "pages", ["http_status"])
    op.create_index("ix_pages_normalized_url", "pages", ["normalized_url"])

    op.create_table(
        "crawl_attempts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["job_id"], ["crawl_jobs.id"], ondelete="CASCADE"),
        sa.CheckConstraint("attempt_number >= 1", name="ck_crawl_attempts_attempt_number_positive"),
        sa.CheckConstraint(
            "status IN ('success', 'failed', 'retrying', 'skipped')",
            name="ck_crawl_attempts_status",
        ),
        sa.CheckConstraint(
            "http_status IS NULL OR http_status BETWEEN 100 AND 599",
            name="ck_crawl_attempts_http_status",
        ),
        sa.CheckConstraint(
            "response_time_ms IS NULL OR response_time_ms >= 0",
            name="ck_crawl_attempts_response_time_nonnegative",
        ),
    )
    op.create_index("ix_crawl_attempts_created_at", "crawl_attempts", ["created_at"])
    op.create_index("ix_crawl_attempts_job_id", "crawl_attempts", ["job_id"])
    op.create_index("ix_crawl_attempts_status", "crawl_attempts", ["status"])

    op.create_table(
        "links",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("source_page_id", sa.BigInteger(), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("target_domain", sa.String(length=255), nullable=True),
        sa.Column("is_internal", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["source_page_id"], ["pages.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("source_page_id", "target_url", name="uq_links_source_target"),
    )
    op.create_index("ix_links_is_internal", "links", ["is_internal"])
    op.create_index("ix_links_source_page_id", "links", ["source_page_id"])
    op.create_index("ix_links_target_domain", "links", ["target_domain"])


def downgrade() -> None:
    op.drop_index("ix_links_target_domain", table_name="links")
    op.drop_index("ix_links_source_page_id", table_name="links")
    op.drop_index("ix_links_is_internal", table_name="links")
    op.drop_table("links")

    op.drop_index("ix_crawl_attempts_status", table_name="crawl_attempts")
    op.drop_index("ix_crawl_attempts_job_id", table_name="crawl_attempts")
    op.drop_index("ix_crawl_attempts_created_at", table_name="crawl_attempts")
    op.drop_table("crawl_attempts")

    op.drop_index("ix_pages_normalized_url", table_name="pages")
    op.drop_index("ix_pages_http_status", table_name="pages")
    op.drop_index("ix_pages_domain_created_at", table_name="pages")
    op.drop_index("ix_pages_domain", table_name="pages")
    op.drop_index("ix_pages_created_at", table_name="pages")
    op.drop_index("ix_pages_content_hash", table_name="pages")
    op.drop_table("pages")

    op.drop_index("ix_crawl_jobs_status", table_name="crawl_jobs")
    op.drop_index("ix_crawl_jobs_created_at", table_name="crawl_jobs")
    op.drop_table("crawl_jobs")
