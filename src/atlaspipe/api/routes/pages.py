from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from atlaspipe.api.dependencies import repository_dependency
from atlaspipe.db.repositories import PageRepository
from atlaspipe.schemas.page import PageListResponse, PageRecord

router = APIRouter(tags=["pages"])
RepositoryDependency = Depends(repository_dependency)


@router.get("/pages", response_model=PageListResponse)
async def list_pages(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    domain: str | None = None,
    http_status: int | None = Query(default=None, ge=100, le=599),
    repository: PageRepository = RepositoryDependency,
) -> PageListResponse:
    pages, total = await repository.list_pages(
        limit=limit,
        offset=offset,
        domain=domain,
        http_status=http_status,
    )
    return PageListResponse(items=pages, limit=limit, offset=offset, total=total)


@router.get("/pages/{page_id}", response_model=PageRecord)
async def get_page(
    page_id: int,
    repository: PageRepository = RepositoryDependency,
) -> PageRecord:
    page = await repository.get_page(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="page not found")
    return page


@router.get("/domains/{domain}", response_model=list[PageRecord])
async def get_domain(
    domain: str,
    limit: int = Query(default=50, ge=1, le=500),
    repository: PageRepository = RepositoryDependency,
) -> list[PageRecord]:
    return await repository.get_domain_pages(domain, limit=limit)
