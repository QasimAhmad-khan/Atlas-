from __future__ import annotations

import asyncio

from atlaspipe.db.repositories import InMemoryRepository
from atlaspipe.schemas.page import PageRecord


async def main() -> None:
    repository = InMemoryRepository.empty()
    await repository.save_pages(
        [
            PageRecord(
                url="https://example.com",
                normalized_url="https://example.com/",
                domain="example.com",
                title="Example Domain",
                http_status=200,
            )
        ]
    )
    stats = await repository.stats()
    print(stats.model_dump())


if __name__ == "__main__":
    asyncio.run(main())
