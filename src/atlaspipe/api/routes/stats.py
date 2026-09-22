from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from atlaspipe.api.dependencies import repository_dependency
from atlaspipe.db.repositories import PageRepository
from atlaspipe.observability.metrics import Metrics
from atlaspipe.schemas.stats import DomainStats, StatsResponse, StatusCodeStats

router = APIRouter(tags=["stats"])
RepositoryDependency = Depends(repository_dependency)


@router.get("/stats", response_model=StatsResponse)
async def stats(repository: PageRepository = RepositoryDependency) -> StatsResponse:
    return await repository.stats()


@router.get("/stats/domains", response_model=list[DomainStats])
async def domain_stats(
    repository: PageRepository = RepositoryDependency,
) -> list[DomainStats]:
    return await repository.domain_stats()


@router.get("/stats/status-codes", response_model=list[StatusCodeStats])
async def status_code_stats(
    repository: PageRepository = RepositoryDependency,
) -> list[StatusCodeStats]:
    return await repository.status_code_stats()


@router.get("/metrics")
async def metrics(request: Request) -> dict[str, float | int]:
    current = getattr(request.app.state, "metrics", None)
    if current is None:
        current = Metrics()
        request.app.state.metrics = current
    return current.snapshot()
