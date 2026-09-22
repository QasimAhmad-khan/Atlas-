from __future__ import annotations

from atlaspipe.db.models import metadata_summary


def test_database_metadata_declares_required_tables() -> None:
    summary = metadata_summary()
    assert summary["tables"] == ["crawl_attempts", "crawl_jobs", "links", "pages"]


def test_database_metadata_declares_required_indexes() -> None:
    indexes = metadata_summary()["indexes"]
    assert "ix_pages_normalized_url" in indexes["pages"]
    assert "ix_pages_domain" in indexes["pages"]
    assert "ix_pages_content_hash" in indexes["pages"]
    assert "ix_crawl_jobs_status" in indexes["crawl_jobs"]


def test_database_metadata_declares_required_constraints() -> None:
    constraints = metadata_summary()["constraints"]
    assert "uq_pages_normalized_url" in constraints["pages"]
    assert "uq_links_source_target" in constraints["links"]
    assert "ck_crawl_jobs_status" in constraints["crawl_jobs"]
