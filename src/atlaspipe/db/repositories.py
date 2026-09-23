from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import NotRequired, Protocol, TypedDict
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import and_, case, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from atlaspipe.db.models import CrawlAttempt, CrawlFrontierItem, CrawlJob, DomainStat, Page
from atlaspipe.pipeline.normalization import normalize_url
from atlaspipe.schemas.crawl import CrawlJobResponse
from atlaspipe.schemas.page import PageRecord
from atlaspipe.schemas.stats import DomainStats, StatsResponse, StatusCodeStats


class Repository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session


@dataclass(frozen=True)
class FrontierLease:
    id: int
    job_id: int
    url: str
    normalized_url: str
    domain: str
    attempt_count: int
    lease_owner: str
    lease_token: str
    lease_expires_at: datetime


@dataclass(frozen=True)
class FrontierStats:
    pending: int = 0
    leased: int = 0
    complete: int = 0
    failed: int = 0
    dead: int = 0

    @property
    def accounted_for(self) -> int:
        return self.complete + self.dead


class InMemoryFrontierItem(TypedDict):
    id: int
    job_id: int
    url: str
    normalized_url: str
    domain: str
    priority: int
    state: str
    attempt_count: int
    max_attempts: int
    available_at: datetime
    lease_owner: str | None
    lease_token: str | None
    lease_expires_at: datetime | None
    last_error_type: NotRequired[str]
    last_error_message: NotRequired[str]


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

    async def save_page_and_complete_frontier_item(
        self,
        *,
        item_id: int,
        lease_owner: str,
        lease_token: str,
        page: PageRecord,
    ) -> bool: ...

    async def stats(self) -> StatsResponse: ...

    async def domain_stats(self) -> list[DomainStats]: ...

    async def status_code_stats(self) -> list[StatusCodeStats]: ...

    async def refresh_domain_stats(self) -> int: ...

    async def schedule_frontier_urls(
        self,
        *,
        job_id: int,
        urls: list[str],
        priority: int = 0,
        max_attempts: int = 3,
    ) -> int: ...

    async def acquire_frontier_batch(
        self,
        *,
        owner: str,
        batch_size: int,
        lease_seconds: int,
    ) -> list[FrontierLease]: ...

    async def complete_frontier_item(
        self,
        item_id: int,
        *,
        lease_owner: str,
        lease_token: str,
    ) -> bool: ...

    async def renew_frontier_lease(
        self,
        item_id: int,
        *,
        lease_owner: str,
        lease_token: str,
        extend_seconds: int,
    ) -> bool: ...

    async def fail_frontier_item(
        self,
        item_id: int,
        *,
        lease_owner: str,
        lease_token: str,
        error_type: str,
        error_message: str,
        retry_after_seconds: int = 0,
    ) -> bool: ...

    async def frontier_stats(self, *, job_id: int | None = None) -> FrontierStats: ...


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
        if not pages:
            return 0
        rows = [record.model_dump(exclude={"id"}, exclude_none=True) for record in pages]
        statement = pg_insert(Page).values(rows)
        update_values = {
            "url": statement.excluded.url,
            "canonical_url": statement.excluded.canonical_url,
            "domain": statement.excluded.domain,
            "title": statement.excluded.title,
            "description": statement.excluded.description,
            "http_status": statement.excluded.http_status,
            "content_type": statement.excluded.content_type,
            "content_length": statement.excluded.content_length,
            "html_hash": statement.excluded.html_hash,
            "content_hash": statement.excluded.content_hash,
            "internal_link_count": statement.excluded.internal_link_count,
            "external_link_count": statement.excluded.external_link_count,
            "outbound_link_count": statement.excluded.outbound_link_count,
            "response_time_ms": statement.excluded.response_time_ms,
            "last_seen_at": func.now(),
            "updated_at": func.now(),
        }
        result = await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[Page.normalized_url],
                set_=update_values,
            )
        )
        await self._session.flush()
        return _rowcount(result)

    async def schedule_frontier_urls(
        self,
        *,
        job_id: int,
        urls: list[str],
        priority: int = 0,
        max_attempts: int = 3,
    ) -> int:
        if not urls:
            return 0
        rows: list[dict[str, str | int]] = []
        for url in urls:
            normalized = normalize_url(url)
            rows.append(
                {
                    "job_id": job_id,
                    "url": url,
                    "normalized_url": normalized,
                    "domain": urlsplit(normalized).hostname or "",
                    "priority": priority,
                    "max_attempts": max_attempts,
                }
            )
        scheduled = 0
        for chunk in _chunks(rows, 5_000):
            statement = (
                pg_insert(CrawlFrontierItem)
                .values(chunk)
                .on_conflict_do_nothing(
                    index_elements=[CrawlFrontierItem.job_id, CrawlFrontierItem.normalized_url]
                )
            )
            result = await self._session.execute(statement)
            scheduled += _rowcount(result)
        await self._session.flush()
        return scheduled

    async def acquire_frontier_batch(
        self,
        *,
        owner: str,
        batch_size: int,
        lease_seconds: int,
    ) -> list[FrontierLease]:
        now = datetime.now(UTC)
        await self._mark_expired_exhausted_leases_dead(now)
        lease_expires_at = now + timedelta(seconds=lease_seconds)
        rows = (
            await self._session.scalars(
                select(CrawlFrontierItem)
                .where(
                    or_(
                        and_(
                            CrawlFrontierItem.state == "pending",
                            CrawlFrontierItem.available_at <= now,
                        ),
                        and_(
                            CrawlFrontierItem.state == "leased",
                            CrawlFrontierItem.lease_expires_at < now,
                        ),
                    ),
                    CrawlFrontierItem.attempt_count < CrawlFrontierItem.max_attempts,
                )
                .order_by(
                    CrawlFrontierItem.priority.desc(),
                    CrawlFrontierItem.created_at,
                    CrawlFrontierItem.id,
                )
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for item in rows:
            lease_token = uuid4().hex
            item.state = "leased"
            item.lease_owner = owner
            item.lease_token = lease_token
            item.lease_expires_at = lease_expires_at
            item.attempt_count += 1
            item.updated_at = now
            item.last_error_type = None
            item.last_error_message = None
        await self._session.flush()
        return [
            FrontierLease(
                id=item.id,
                job_id=item.job_id,
                url=item.url,
                normalized_url=item.normalized_url,
                domain=item.domain,
                attempt_count=item.attempt_count,
                lease_owner=owner,
                lease_token=item.lease_token or "",
                lease_expires_at=lease_expires_at,
            )
            for item in rows
        ]

    async def _mark_expired_exhausted_leases_dead(self, now: datetime) -> None:
        await self._session.execute(
            update(CrawlFrontierItem)
            .where(
                CrawlFrontierItem.state == "leased",
                CrawlFrontierItem.lease_expires_at < now,
                CrawlFrontierItem.attempt_count >= CrawlFrontierItem.max_attempts,
            )
            .values(
                state="dead",
                available_at=now,
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                last_error_type="LeaseExpired",
                last_error_message="lease expired after retry budget was exhausted",
                updated_at=now,
            )
        )

    async def complete_frontier_item(
        self,
        item_id: int,
        *,
        lease_owner: str,
        lease_token: str,
    ) -> bool:
        now = datetime.now(UTC)
        result = await self._session.execute(
            update(CrawlFrontierItem)
            .where(
                CrawlFrontierItem.id == item_id,
                CrawlFrontierItem.state == "leased",
                CrawlFrontierItem.lease_owner == lease_owner,
                CrawlFrontierItem.lease_token == lease_token,
                CrawlFrontierItem.lease_expires_at > now,
            )
            .values(
                state="complete",
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                completed_at=now,
                updated_at=now,
            )
        )
        await self._session.flush()
        return bool(_rowcount(result))

    async def renew_frontier_lease(
        self,
        item_id: int,
        *,
        lease_owner: str,
        lease_token: str,
        extend_seconds: int,
    ) -> bool:
        now = datetime.now(UTC)
        result = await self._session.execute(
            update(CrawlFrontierItem)
            .where(
                CrawlFrontierItem.id == item_id,
                CrawlFrontierItem.state == "leased",
                CrawlFrontierItem.lease_owner == lease_owner,
                CrawlFrontierItem.lease_token == lease_token,
                CrawlFrontierItem.lease_expires_at > now,
            )
            .values(
                lease_expires_at=now + timedelta(seconds=extend_seconds),
                updated_at=now,
            )
        )
        await self._session.flush()
        return bool(_rowcount(result))

    async def save_page_and_complete_frontier_item(
        self,
        *,
        item_id: int,
        lease_owner: str,
        lease_token: str,
        page: PageRecord,
    ) -> bool:
        now = datetime.now(UTC)
        item = await self._session.scalar(
            select(CrawlFrontierItem)
            .where(
                CrawlFrontierItem.id == item_id,
                CrawlFrontierItem.state == "leased",
                CrawlFrontierItem.lease_owner == lease_owner,
                CrawlFrontierItem.lease_token == lease_token,
                CrawlFrontierItem.lease_expires_at > now,
            )
            .with_for_update()
        )
        if item is None:
            return False

        await self.save_pages([page])
        item.state = "complete"
        item.lease_owner = None
        item.lease_token = None
        item.lease_expires_at = None
        item.completed_at = now
        item.updated_at = now
        await self._session.flush()
        return True

    async def fail_frontier_item(
        self,
        item_id: int,
        *,
        lease_owner: str,
        lease_token: str,
        error_type: str,
        error_message: str,
        retry_after_seconds: int = 0,
    ) -> bool:
        item = await self._session.scalar(
            select(CrawlFrontierItem)
            .where(
                CrawlFrontierItem.id == item_id,
                CrawlFrontierItem.state == "leased",
                CrawlFrontierItem.lease_owner == lease_owner,
                CrawlFrontierItem.lease_token == lease_token,
                CrawlFrontierItem.lease_expires_at > datetime.now(UTC),
            )
            .with_for_update()
        )
        if item is None:
            return False
        now = datetime.now(UTC)
        should_retry = item.attempt_count < item.max_attempts
        item.state = "pending" if should_retry else "dead"
        item.available_at = now + timedelta(seconds=retry_after_seconds) if should_retry else now
        item.lease_owner = None
        item.lease_token = None
        item.lease_expires_at = None
        item.last_error_type = error_type
        item.last_error_message = error_message[:2000]
        item.updated_at = now
        await self._session.flush()
        return True

    async def frontier_stats(self, *, job_id: int | None = None) -> FrontierStats:
        statement = select(CrawlFrontierItem.state, func.count()).group_by(CrawlFrontierItem.state)
        if job_id is not None:
            statement = statement.where(CrawlFrontierItem.job_id == job_id)
        rows = (await self._session.execute(statement)).all()
        counts = {state: int(count) for state, count in rows}
        return FrontierStats(
            pending=counts.get("pending", 0),
            leased=counts.get("leased", 0),
            complete=counts.get("complete", 0),
            failed=counts.get("failed", 0),
            dead=counts.get("dead", 0),
        )

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
        rollup_count = int(
            await self._session.scalar(select(func.count()).select_from(DomainStat)) or 0
        )
        if rollup_count > 0:
            rollup_rows = (
                await self._session.scalars(
                    select(DomainStat).order_by(DomainStat.page_count.desc(), DomainStat.domain)
                )
            ).all()
            return [DomainStats(domain=row.domain, pages=row.page_count) for row in rollup_rows]

        aggregate_rows = (
            await self._session.execute(
                select(Page.domain, func.count())
                .group_by(Page.domain)
                .order_by(func.count().desc())
            )
        ).all()
        return [DomainStats(domain=row[0], pages=row[1]) for row in aggregate_rows]

    async def refresh_domain_stats(self) -> int:
        await self._session.execute(delete(DomainStat))
        rows = (
            await self._session.execute(
                select(
                    Page.domain,
                    func.count().label("page_count"),
                    func.sum(case((Page.http_status.between(200, 399), 1), else_=0)).label(
                        "success_count"
                    ),
                    func.sum(case((Page.http_status >= 400, 1), else_=0)).label("failure_count"),
                    func.coalesce(func.sum(Page.content_length), 0).label("total_bytes"),
                    func.count(func.distinct(Page.content_hash)).label("unique_content_hashes"),
                    func.max(Page.last_seen_at).label("last_crawled_at"),
                ).group_by(Page.domain)
            )
        ).all()
        now = datetime.now(UTC)
        stats = [
            DomainStat(
                domain=row.domain,
                page_count=row.page_count,
                success_count=row.success_count,
                failure_count=row.failure_count,
                total_bytes=row.total_bytes,
                unique_content_hashes=row.unique_content_hashes,
                last_crawled_at=row.last_crawled_at,
                refreshed_at=now,
            )
            for row in rows
        ]
        self._session.add_all(stats)
        await self._session.flush()
        return len(stats)

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
    frontier: dict[int, InMemoryFrontierItem]
    next_job_id: int = 1
    next_page_id: int = 1
    next_frontier_id: int = 1

    @classmethod
    def empty(cls) -> InMemoryRepository:
        return cls(jobs={}, pages={}, frontier={})

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

    async def refresh_domain_stats(self) -> int:
        return len({page.domain for page in self.pages.values()})

    async def schedule_frontier_urls(
        self,
        *,
        job_id: int,
        urls: list[str],
        priority: int = 0,
        max_attempts: int = 3,
    ) -> int:
        existing = {(item["job_id"], item["normalized_url"]) for item in self.frontier.values()}
        scheduled = 0
        for url in urls:
            normalized = normalize_url(url)
            key = (job_id, normalized)
            if key in existing:
                continue
            self.frontier[self.next_frontier_id] = {
                "id": self.next_frontier_id,
                "job_id": job_id,
                "url": url,
                "normalized_url": normalized,
                "domain": urlsplit(normalized).hostname or "",
                "priority": priority,
                "state": "pending",
                "attempt_count": 0,
                "max_attempts": max_attempts,
                "available_at": datetime.now(UTC),
                "lease_owner": None,
                "lease_token": None,
                "lease_expires_at": None,
            }
            self.next_frontier_id += 1
            scheduled += 1
            existing.add(key)
        return scheduled

    async def acquire_frontier_batch(
        self,
        *,
        owner: str,
        batch_size: int,
        lease_seconds: int,
    ) -> list[FrontierLease]:
        now = datetime.now(UTC)
        for item in self.frontier.values():
            if (
                item["state"] == "leased"
                and item["attempt_count"] >= item["max_attempts"]
                and item["lease_expires_at"] is not None
                and item["lease_expires_at"] < now
            ):
                item["state"] = "dead"
                item["available_at"] = now
                item["lease_owner"] = None
                item["lease_token"] = None
                item["lease_expires_at"] = None
                item["last_error_type"] = "LeaseExpired"
                item["last_error_message"] = "lease expired after retry budget was exhausted"
        lease_expires_at = now + timedelta(seconds=lease_seconds)
        claimable = [
            item
            for item in self.frontier.values()
            if item["attempt_count"] < item["max_attempts"] and _in_memory_item_is_due(item, now)
        ]
        claimable.sort(key=lambda item: (-item["priority"], item["id"]))
        leases: list[FrontierLease] = []
        for item in claimable[:batch_size]:
            lease_token = uuid4().hex
            item["state"] = "leased"
            item["lease_owner"] = owner
            item["lease_token"] = lease_token
            item["lease_expires_at"] = lease_expires_at
            item["attempt_count"] += 1
            leases.append(
                FrontierLease(
                    id=item["id"],
                    job_id=item["job_id"],
                    url=item["url"],
                    normalized_url=item["normalized_url"],
                    domain=item["domain"],
                    attempt_count=item["attempt_count"],
                    lease_owner=owner,
                    lease_token=lease_token,
                    lease_expires_at=lease_expires_at,
                )
            )
        return leases

    async def complete_frontier_item(
        self,
        item_id: int,
        *,
        lease_owner: str,
        lease_token: str,
    ) -> bool:
        item = self.frontier.get(item_id)
        if item is None:
            return False
        if (
            item["state"] != "leased"
            or item["lease_owner"] != lease_owner
            or item["lease_token"] != lease_token
            or not _lease_is_unexpired(item)
        ):
            return False
        item["state"] = "complete"
        item["lease_owner"] = None
        item["lease_token"] = None
        item["lease_expires_at"] = None
        return True

    async def renew_frontier_lease(
        self,
        item_id: int,
        *,
        lease_owner: str,
        lease_token: str,
        extend_seconds: int,
    ) -> bool:
        item = self.frontier.get(item_id)
        if item is None:
            return False
        if (
            item["state"] != "leased"
            or item["lease_owner"] != lease_owner
            or item["lease_token"] != lease_token
            or not _lease_is_unexpired(item)
        ):
            return False
        item["lease_expires_at"] = datetime.now(UTC) + timedelta(seconds=extend_seconds)
        return True

    async def save_page_and_complete_frontier_item(
        self,
        *,
        item_id: int,
        lease_owner: str,
        lease_token: str,
        page: PageRecord,
    ) -> bool:
        item = self.frontier.get(item_id)
        if item is None:
            return False
        if (
            item["state"] != "leased"
            or item["lease_owner"] != lease_owner
            or item["lease_token"] != lease_token
            or not _lease_is_unexpired(item)
        ):
            return False
        await self.save_pages([page])
        item["state"] = "complete"
        item["lease_owner"] = None
        item["lease_token"] = None
        item["lease_expires_at"] = None
        return True

    async def fail_frontier_item(
        self,
        item_id: int,
        *,
        lease_owner: str,
        lease_token: str,
        error_type: str,
        error_message: str,
        retry_after_seconds: int = 0,
    ) -> bool:
        item = self.frontier.get(item_id)
        if item is None:
            return False
        if (
            item["state"] != "leased"
            or item["lease_owner"] != lease_owner
            or item["lease_token"] != lease_token
            or not _lease_is_unexpired(item)
        ):
            return False
        should_retry = item["attempt_count"] < item["max_attempts"]
        item["state"] = "pending" if should_retry else "dead"
        item["available_at"] = datetime.now(UTC) + timedelta(seconds=retry_after_seconds)
        item["lease_owner"] = None
        item["lease_token"] = None
        item["lease_expires_at"] = None
        item["last_error_type"] = error_type
        item["last_error_message"] = error_message
        return True

    async def frontier_stats(self, *, job_id: int | None = None) -> FrontierStats:
        items = list(self.frontier.values())
        if job_id is not None:
            items = [item for item in items if item["job_id"] == job_id]
        counts = Counter(str(item["state"]) for item in items)
        return FrontierStats(
            pending=counts.get("pending", 0),
            leased=counts.get("leased", 0),
            complete=counts.get("complete", 0),
            failed=counts.get("failed", 0),
            dead=counts.get("dead", 0),
        )


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


def _rowcount(result: object) -> int:
    value = getattr(result, "rowcount", 0)
    return value if isinstance(value, int) else 0


def _chunks[T](items: list[T], size: int) -> list[list[T]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _in_memory_item_is_due(item: InMemoryFrontierItem, now: datetime) -> bool:
    if item["state"] == "pending":
        return item["available_at"] <= now
    if item["state"] == "leased":
        lease_expires_at = item["lease_expires_at"]
        return lease_expires_at is not None and lease_expires_at < now
    return False


def _lease_is_unexpired(item: InMemoryFrontierItem) -> bool:
    lease_expires_at = item["lease_expires_at"]
    return lease_expires_at is not None and lease_expires_at > datetime.now(UTC)
