from __future__ import annotations

from fastapi import APIRouter, Depends

from atlaspipe.api.dependencies import repository_dependency
from atlaspipe.db.repositories import PageRepository
from atlaspipe.schemas.crawl import CrawlJobResponse, CrawlRequest

router = APIRouter(tags=["crawl"])
RepositoryDependency = Depends(repository_dependency)


@router.post("/crawl", response_model=CrawlJobResponse, status_code=202)
async def create_crawl(
    request: CrawlRequest,
    repository: PageRepository = RepositoryDependency,
) -> CrawlJobResponse:
    return await repository.create_job([str(url) for url in request.urls])


@router.get("/jobs/{job_id}", response_model=CrawlJobResponse)
async def get_job(
    job_id: int,
    repository: PageRepository = RepositoryDependency,
) -> CrawlJobResponse:
    job = await repository.get_job(job_id)
    if job is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="job not found")
    return job
