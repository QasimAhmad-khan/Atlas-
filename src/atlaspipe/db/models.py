from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class CrawlJob(TimestampMixin, Base):
    __tablename__ = "crawl_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'pending', 'running', 'completed', 'completed_with_errors', "
            "'failed', 'cancelled'"
            ")",
            name="ck_crawl_jobs_status",
        ),
        CheckConstraint("processed_count >= 0", name="ck_crawl_jobs_processed_count_nonnegative"),
        CheckConstraint("success_count >= 0", name="ck_crawl_jobs_success_count_nonnegative"),
        CheckConstraint("failure_count >= 0", name="ck_crawl_jobs_failure_count_nonnegative"),
        Index("ix_crawl_jobs_created_at", "created_at"),
        Index("ix_crawl_jobs_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_urls: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    attempts: Mapped[list[CrawlAttempt]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )
    frontier_items: Mapped[list[CrawlFrontierItem]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )


class CrawlFrontierItem(TimestampMixin, Base):
    __tablename__ = "crawl_frontier"
    __table_args__ = (
        UniqueConstraint("job_id", "normalized_url", name="uq_crawl_frontier_job_url"),
        CheckConstraint(
            "state IN ('pending', 'leased', 'complete', 'failed', 'dead')",
            name="ck_crawl_frontier_state",
        ),
        CheckConstraint("priority >= 0", name="ck_crawl_frontier_priority_nonnegative"),
        CheckConstraint("attempt_count >= 0", name="ck_crawl_frontier_attempt_count_nonnegative"),
        CheckConstraint("max_attempts >= 1", name="ck_crawl_frontier_max_attempts_positive"),
        Index(
            "ix_crawl_frontier_claimable",
            "state",
            "available_at",
            "priority",
            "created_at",
        ),
        Index("ix_crawl_frontier_domain_state_available", "domain", "state", "available_at"),
        Index("ix_crawl_frontier_job_state", "job_id", "state"),
        Index("ix_crawl_frontier_lease_expires_at", "lease_expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("crawl_jobs.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    state: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_type: Mapped[str | None] = mapped_column(String(128))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    job: Mapped[CrawlJob] = relationship(back_populates="frontier_items")


class Page(TimestampMixin, Base):
    __tablename__ = "pages"
    __table_args__ = (
        UniqueConstraint("normalized_url", name="uq_pages_normalized_url"),
        CheckConstraint(
            "http_status IS NULL OR http_status BETWEEN 100 AND 599",
            name="ck_pages_http_status",
        ),
        CheckConstraint(
            "content_length IS NULL OR content_length >= 0",
            name="ck_pages_content_length_nonnegative",
        ),
        CheckConstraint(
            "internal_link_count >= 0",
            name="ck_pages_internal_link_count_nonnegative",
        ),
        CheckConstraint(
            "external_link_count >= 0",
            name="ck_pages_external_link_count_nonnegative",
        ),
        CheckConstraint(
            "outbound_link_count >= 0",
            name="ck_pages_outbound_link_count_nonnegative",
        ),
        CheckConstraint(
            "response_time_ms IS NULL OR response_time_ms >= 0",
            name="ck_pages_response_time_nonnegative",
        ),
        Index("ix_pages_content_hash", "content_hash"),
        Index("ix_pages_created_at", "created_at"),
        Index("ix_pages_domain", "domain"),
        Index("ix_pages_domain_created_at", "domain", "created_at"),
        Index("ix_pages_http_status", "http_status"),
        Index("ix_pages_normalized_url", "normalized_url"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(255))
    content_length: Mapped[int | None] = mapped_column(BigInteger)
    html_hash: Mapped[str | None] = mapped_column(String(64))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    internal_link_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    external_link_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    outbound_link_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    links: Mapped[list[Link]] = relationship(
        back_populates="source_page",
        cascade="all, delete-orphan",
    )


class DomainStat(Base):
    __tablename__ = "domain_stats"
    __table_args__ = (
        CheckConstraint("page_count >= 0", name="ck_domain_stats_page_count_nonnegative"),
        CheckConstraint("success_count >= 0", name="ck_domain_stats_success_count_nonnegative"),
        CheckConstraint("failure_count >= 0", name="ck_domain_stats_failure_count_nonnegative"),
        CheckConstraint("total_bytes >= 0", name="ck_domain_stats_total_bytes_nonnegative"),
        CheckConstraint(
            "unique_content_hashes >= 0",
            name="ck_domain_stats_unique_content_hashes_nonnegative",
        ),
        Index("ix_domain_stats_page_count", "page_count"),
        Index("ix_domain_stats_last_crawled_at", "last_crawled_at"),
    )

    domain: Mapped[str] = mapped_column(String(255), primary_key=True)
    page_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    success_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    failure_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    unique_content_hashes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class CrawlAttempt(TimestampMixin, Base):
    __tablename__ = "crawl_attempts"
    __table_args__ = (
        CheckConstraint(
            "attempt_number >= 1",
            name="ck_crawl_attempts_attempt_number_positive",
        ),
        CheckConstraint(
            "status IN ('success', 'failed', 'retrying', 'skipped')",
            name="ck_crawl_attempts_status",
        ),
        CheckConstraint(
            "http_status IS NULL OR http_status BETWEEN 100 AND 599",
            name="ck_crawl_attempts_http_status",
        ),
        CheckConstraint(
            "response_time_ms IS NULL OR response_time_ms >= 0",
            name="ck_crawl_attempts_response_time_nonnegative",
        ),
        Index("ix_crawl_attempts_created_at", "created_at"),
        Index("ix_crawl_attempts_job_id", "job_id"),
        Index("ix_crawl_attempts_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("crawl_jobs.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(Text, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    error_type: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)

    job: Mapped[CrawlJob] = relationship(back_populates="attempts")


class Link(Base):
    __tablename__ = "links"
    __table_args__ = (
        UniqueConstraint("source_page_id", "target_url", name="uq_links_source_target"),
        Index("ix_links_is_internal", "is_internal"),
        Index("ix_links_source_page_id", "source_page_id"),
        Index("ix_links_target_domain", "target_domain"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"))
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    target_domain: Mapped[str | None] = mapped_column(String(255))
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False)

    source_page: Mapped[Page] = relationship(back_populates="links")


def table_names() -> set[str]:
    return set(Base.metadata.tables)


def model_indexes() -> dict[str, set[str]]:
    return {
        table.name: {index.name for index in table.indexes if index.name is not None}
        for table in Base.metadata.sorted_tables
    }


def model_constraints() -> dict[str, set[str]]:
    constraints: dict[str, set[str]] = {}
    for table in Base.metadata.sorted_tables:
        constraints[table.name] = set()
        for constraint in table.constraints:
            if constraint.name is not None:
                constraints[table.name].add(str(constraint.name))
    return constraints


def metadata_summary() -> dict[str, Any]:
    return {
        "tables": sorted(table_names()),
        "indexes": model_indexes(),
        "constraints": model_constraints(),
    }
