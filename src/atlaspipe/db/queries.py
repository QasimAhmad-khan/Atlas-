from __future__ import annotations

from sqlalchemy import select

from atlaspipe.db.models import CrawlJob, Page

select_recent_pages = select(Page).order_by(Page.created_at.desc())
select_pending_jobs = select(CrawlJob).where(CrawlJob.status == "pending")
