"""Exercise the built image's dependencies, auth and real PostgreSQL connection."""

from __future__ import annotations

import secrets

import httpx
import uvloop

from atlaspipe.api.app import create_app
from atlaspipe.config import Settings


async def main() -> None:
    settings = Settings(api_key=secrets.token_hex(32), metrics_key=secrets.token_hex(32))
    app = create_app(settings=settings)
    bearer = {"Authorization": f"Bearer {settings.api_key.get_secret_value()}"}
    metrics = {"Authorization": f"Bearer {settings.metrics_key.get_secret_value()}"}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://container"
        ) as client:
            assert (await client.get("/live")).status_code == 200
            assert (await client.get("/ready")).status_code == 200
            assert (await client.get("/stats")).status_code == 401
            assert (await client.get("/stats", headers=bearer)).status_code == 200
            assert (await client.get("/internal/metrics")).status_code == 401
            assert (await client.get("/internal/metrics", headers=metrics)).status_code == 200
            response = await client.post(
                "/crawl",
                json={"urls": [f"https://fixture.example.invalid/{secrets.token_hex(8)}"]},
                headers=bearer,
            )
            assert response.status_code == 202
            job_id = response.json()["id"]
            assert (await client.get(f"/jobs/{job_id}")).status_code == 401
            assert (await client.get(f"/jobs/{job_id}", headers=bearer)).status_code == 200
    print("Container uvloop, PostgreSQL readiness, auth, metrics and durable job smoke passed.")


if __name__ == "__main__":
    uvloop.run(main())
