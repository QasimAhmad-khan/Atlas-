from __future__ import annotations

from fastapi import Request

from atlaspipe.config import Settings, get_settings
from atlaspipe.db.repositories import InMemoryRepository, PageRepository


def settings_dependency() -> Settings:
    return get_settings()


def repository_dependency(request: Request) -> PageRepository:
    repository = getattr(request.app.state, "repository", None)
    if repository is None:
        repository = InMemoryRepository.empty()
        request.app.state.repository = repository
    return repository
