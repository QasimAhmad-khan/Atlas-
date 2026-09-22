from __future__ import annotations

from atlaspipe.db.models import metadata_summary


def test_database_metadata_declares_required_tables() -> None:
    summary = metadata_summary()
    assert summary["tables"] == [
        "crawl_attempts",
        "crawl_frontier",
        "crawl_jobs",
        "domain_stats",
        "links",
        "pages",
    ]


def test_database_metadata_declares_required_indexes() -> None:
    indexes = metadata_summary()["indexes"]
    assert "ix_pages_normalized_url" in indexes["pages"]
    assert "ix_pages_domain" in indexes["pages"]
    assert "ix_pages_content_hash" in indexes["pages"]
    assert "ix_crawl_jobs_status" in indexes["crawl_jobs"]
    assert "ix_crawl_frontier_claimable" in indexes["crawl_frontier"]
    assert "ix_crawl_frontier_lease_expires_at" in indexes["crawl_frontier"]
    assert "ix_domain_stats_page_count" in indexes["domain_stats"]


def test_database_metadata_declares_required_constraints() -> None:
    constraints = metadata_summary()["constraints"]
    assert "uq_pages_normalized_url" in constraints["pages"]
    assert "uq_links_source_target" in constraints["links"]
    assert "ck_crawl_jobs_status" in constraints["crawl_jobs"]
    assert "uq_crawl_frontier_job_url" in constraints["crawl_frontier"]
    assert "ck_crawl_frontier_state" in constraints["crawl_frontier"]
    assert "ck_domain_stats_page_count_nonnegative" in constraints["domain_stats"]
