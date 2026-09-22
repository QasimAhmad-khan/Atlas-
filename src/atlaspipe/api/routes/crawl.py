from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from atlaspipe.api.dependencies import repository_dependency
from atlaspipe.db.repositories import PageRepository
from atlaspipe.pipeline.validation import validate_public_url
from atlaspipe.schemas.crawl import CrawlJobResponse, CrawlRequest

router = APIRouter(tags=["crawl"])
RepositoryDependency = Depends(repository_dependency)


@router.post("/crawl", response_model=CrawlJobResponse, status_code=202)
async def create_crawl(
    request: CrawlRequest,
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
    job = await repository.create_job(urls)
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
