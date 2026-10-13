from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from opentelemetry.propagate import inject

from atlaspipe.api.dependencies import repository_dependency
from atlaspipe.api.security import authorize_write, consume_quota
from atlaspipe.db.repositories import PageRepository
from atlaspipe.pipeline.validation import validate_public_url
from atlaspipe.schemas.crawl import CrawlJobResponse, CrawlRequest

router = APIRouter(tags=["crawl"])
RepositoryDependency = Depends(repository_dependency)


@router.post(
    "/crawl",
    response_model=CrawlJobResponse,
    status_code=202,
    dependencies=[Depends(authorize_write)],
)
async def create_crawl(
    request: CrawlRequest,
    http_request: Request,
    repository: PageRepository = RepositoryDependency,
) -> CrawlJobResponse:
    urls = [str(url) for url in request.urls]
    for url in urls:
        validation = validate_public_url(url)
        if not validation.is_valid:
            raise HTTPException(
                status_code=422,
                detail={"url": url, "reason": validation.reason},
            )
    await consume_quota(http_request, len(urls))
    carrier: dict[str, str] = {}
    inject(carrier)
    job = await repository.create_job(urls, traceparent=carrier.get("traceparent"))
    await repository.schedule_frontier_urls(job_id=job.id, urls=urls)
    return job


@router.get("/jobs/{job_id}", response_model=CrawlJobResponse)
async def get_job(
    job_id: int,
    repository: PageRepository = RepositoryDependency,
) -> CrawlJobResponse:
    job = await repository.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job
