from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from atlaspipe.db.models import CrawlAttempt, CrawlJob, Page
from atlaspipe.schemas.crawl import CrawlJobResponse
from atlaspipe.schemas.page import PageRecord
from atlaspipe.schemas.stats import DomainStats, StatsResponse, StatusCodeStats


class Repository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session


class PageRepository(Protocol):
    async def create_job(self, urls: list[str]) -> CrawlJobResponse: ...

    async def get_job(self, job_id: int) -> CrawlJobResponse | None: ...

    async def list_pages(
        self,
        *,
        limit: int,
        offset: int,
        domain: str | None = None,
        http_status: int | None = None,
    ) -> tuple[list[PageRecord], int]: ...

    async def get_page(self, page_id: int) -> PageRecord | None: ...

    async def get_domain_pages(self, domain: str, *, limit: int) -> list[PageRecord]: ...

    async def save_pages(self, pages: list[PageRecord]) -> int: ...

    async def stats(self) -> StatsResponse: ...

    async def domain_stats(self) -> list[DomainStats]: ...

    async def status_code_stats(self) -> list[StatusCodeStats]: ...


class SqlAlchemyRepository(Repository):
    async def create_job(self, urls: list[str]) -> CrawlJobResponse:
        job = CrawlJob(status="pending", requested_urls=urls)
        self._session.add(job)
        await self._session.flush()
        return _job_response(job)

    async def get_job(self, job_id: int) -> CrawlJobResponse | None:
        job = await self._session.get(CrawlJob, job_id)
        return _job_response(job) if job else None

    async def list_pages(
        self,
        *,
        limit: int,
        offset: int,
        domain: str | None = None,
        http_status: int | None = None,
    ) -> tuple[list[PageRecord], int]:
        statement = select(Page)
        count_statement = select(func.count()).select_from(Page)
        if domain is not None:
            statement = statement.where(Page.domain == domain)
            count_statement = count_statement.where(Page.domain == domain)
        if http_status is not None:
            statement = statement.where(Page.http_status == http_status)
            count_statement = count_statement.where(Page.http_status == http_status)
        statement = statement.order_by(Page.created_at.desc()).offset(offset).limit(limit)

        rows = (await self._session.scalars(statement)).all()
        total = int(await self._session.scalar(count_statement) or 0)
        return [PageRecord.model_validate(row) for row in rows], total

    async def get_page(self, page_id: int) -> PageRecord | None:
        page = await self._session.get(Page, page_id)
        return PageRecord.model_validate(page) if page else None

    async def get_domain_pages(self, domain: str, *, limit: int) -> list[PageRecord]:
        rows = (
            await self._session.scalars(
                select(Page)
                .where(Page.domain == domain)
                .order_by(Page.created_at.desc())
                .limit(limit)
            )
        ).all()
        return [PageRecord.model_validate(row) for row in rows]

    async def save_pages(self, pages: list[PageRecord]) -> int:
        saved = 0
        for record in pages:
            page = Page(**record.model_dump(exclude={"id"}))
            self._session.add(page)
            saved += 1
        await self._session.flush()
        return saved

    async def stats(self) -> StatsResponse:
        pages = int(await self._session.scalar(select(func.count()).select_from(Page)) or 0)
        jobs = int(await self._session.scalar(select(func.count()).select_from(CrawlJob)) or 0)
        failed_attempts = int(
            await self._session.scalar(
                select(func.count())
                .select_from(CrawlAttempt)
                .where(CrawlAttempt.status == "failed")
            )
            or 0
        )
        successful_pages = int(
            await self._session.scalar(
                select(func.count()).select_from(Page).where(Page.http_status.between(200, 399))
            )
            or 0
        )
        return StatsResponse(
            jobs=jobs,
            pages=pages,
            successful_pages=successful_pages,
            failed_attempts=failed_attempts,
        )

    async def domain_stats(self) -> list[DomainStats]:
        rows = (
            await self._session.execute(
                select(Page.domain, func.count())
                .group_by(Page.domain)
                .order_by(func.count().desc())
            )
        ).all()
        return [DomainStats(domain=row[0], pages=row[1]) for row in rows]

    async def status_code_stats(self) -> list[StatusCodeStats]:
        rows = (
            await self._session.execute(
                select(Page.http_status, func.count())
                .where(Page.http_status.is_not(None))
                .group_by(Page.http_status)
                .order_by(Page.http_status)
            )
        ).all()
        return [StatusCodeStats(status_code=row[0], pages=row[1]) for row in rows]


@dataclass
class InMemoryRepository:
    jobs: dict[int, CrawlJobResponse]
    pages: dict[int, PageRecord]
    next_job_id: int = 1
    next_page_id: int = 1

    @classmethod
    def empty(cls) -> InMemoryRepository:
        return cls(jobs={}, pages={})

    async def create_job(self, urls: list[str]) -> CrawlJobResponse:
        job = CrawlJobResponse(
            id=self.next_job_id,
            status="pending",
            requested_urls=urls,
            created_at=datetime.now(UTC),
        )
        self.jobs[job.id] = job
        self.next_job_id += 1
        return job

    async def get_job(self, job_id: int) -> CrawlJobResponse | None:
        return self.jobs.get(job_id)

    async def list_pages(
        self,
        *,
        limit: int,
        offset: int,
        domain: str | None = None,
        http_status: int | None = None,
    ) -> tuple[list[PageRecord], int]:
        records = list(self.pages.values())
        if domain is not None:
            records = [page for page in records if page.domain == domain]
        if http_status is not None:
            records = [page for page in records if page.http_status == http_status]
        records.sort(
            key=lambda page: page.created_at or datetime.min.replace(tzinfo=UTC), reverse=True
        )
        return records[offset : offset + limit], len(records)

    async def get_page(self, page_id: int) -> PageRecord | None:
        return self.pages.get(page_id)

    async def get_domain_pages(self, domain: str, *, limit: int) -> list[PageRecord]:
        pages, _total = await self.list_pages(limit=limit, offset=0, domain=domain)
        return pages

    async def save_pages(self, pages: list[PageRecord]) -> int:
        now = datetime.now(UTC)
        saved = 0
        existing_urls = {page.normalized_url for page in self.pages.values()}
        for page in pages:
            if page.normalized_url in existing_urls:
                continue
            record = page.model_copy(
                update={
                    "id": self.next_page_id,
                    "created_at": page.created_at or now,
                    "updated_at": page.updated_at or now,
                    "first_seen_at": page.first_seen_at or now,
                    "last_seen_at": page.last_seen_at or now,
                }
            )
            self.pages[self.next_page_id] = record
            self.next_page_id += 1
            saved += 1
            existing_urls.add(record.normalized_url)
        return saved

    async def stats(self) -> StatsResponse:
        return StatsResponse(
            jobs=len(self.jobs),
            pages=len(self.pages),
            successful_pages=sum(
                1
                for page in self.pages.values()
                if page.http_status is not None and 200 <= page.http_status < 400
            ),
            failed_attempts=0,
        )

    async def domain_stats(self) -> list[DomainStats]:
        counts = Counter(page.domain for page in self.pages.values())
        return [DomainStats(domain=domain, pages=count) for domain, count in counts.most_common()]

    async def status_code_stats(self) -> list[StatusCodeStats]:
        counts = Counter(
            page.http_status for page in self.pages.values() if page.http_status is not None
        )
        return [
            StatusCodeStats(status_code=int(status), pages=count)
            for status, count in sorted(counts.items())
        ]


def _job_response(job: CrawlJob) -> CrawlJobResponse:
    return CrawlJobResponse(
        id=job.id,
        status=job.status,
        requested_urls=job.requested_urls,
        processed_count=job.processed_count,
        success_count=job.success_count,
        failure_count=job.failure_count,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )
