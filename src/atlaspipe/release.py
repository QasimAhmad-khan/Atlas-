"""Protected-environment ECS release orchestration; never runs automatically on import."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx


def register_revision(ecs: Any, arn: str, image: str, *, broken: bool = False) -> str:
    definition = ecs.describe_task_definition(taskDefinition=arn)["taskDefinition"]
    allowed = {
        "family",
        "taskRoleArn",
        "executionRoleArn",
        "networkMode",
        "containerDefinitions",
        "volumes",
        "placementConstraints",
        "requiresCompatibilities",
        "cpu",
        "memory",
        "pidMode",
        "ipcMode",
        "proxyConfiguration",
        "ephemeralStorage",
        "runtimePlatform",
    }
    payload = {key: value for key, value in definition.items() if key in allowed}
    for container in payload["containerDefinitions"]:
        if container["name"] != "app":
            continue
        container["image"] = image
        digest = image.split("@", 1)[1]
        environment = [
            item for item in container.get("environment", []) if item["name"] != "RELEASE"
        ]
        container["environment"] = [*environment, {"name": "RELEASE", "value": digest}]
        if broken:
            container["command"] = ["python", "-c", "raise SystemExit(1)"]
    return str(ecs.register_task_definition(**payload)["taskDefinition"]["taskDefinitionArn"])


def verify_revisions(ecs: Any, cluster: str, expected: dict[str, dict[str, Any]]) -> None:
    response = ecs.describe_services(cluster=cluster, services=list(expected))
    if response.get("failures") or len(response["services"]) != len(expected):
        raise RuntimeError("services are missing")
    for service in response["services"]:
        target = expected[service["serviceName"]]
        primary = next((d for d in service["deployments"] if d["status"] == "PRIMARY"), None)
        if not primary or primary["taskDefinition"] != target["taskDefinition"]:
            raise RuntimeError(
                "requested revision did not become primary (possibly automatic rollback)"
            )
        if (
            primary.get("rolloutState") != "COMPLETED"
            or service["runningCount"] != target["desiredCount"]
            or service["pendingCount"]
        ):
            raise RuntimeError("deployment is not healthy and stable")


def migrate(ecs: Any, config: dict[str, Any], arn: str) -> str:
    response = ecs.run_task(
        cluster=config["cluster"],
        taskDefinition=arn,
        launchType="FARGATE",
        platformVersion="1.4.0",
        networkConfiguration=config["network"],
    )
    if response.get("failures") or len(response.get("tasks", [])) != 1:
        raise RuntimeError("migration task did not start")
    task = response["tasks"][0]["taskArn"]
    try:
        ecs.get_waiter("tasks_stopped").wait(
            cluster=config["cluster"], tasks=[task], WaiterConfig={"Delay": 10, "MaxAttempts": 60}
        )
        result = ecs.describe_tasks(cluster=config["cluster"], tasks=[task])
        containers = result["tasks"][0].get("containers", [])
        if not containers or any(c.get("exitCode") != 0 for c in containers):
            raise RuntimeError("migration task failed")
    except Exception:
        ecs.stop_task(
            cluster=config["cluster"], task=task, reason="migration gate failed or timed out"
        )
        raise
    return str(task)


def smoke(base_url: str, key: str, crawl_url: str, digest: str) -> dict[str, Any]:
    if not base_url.startswith("https://") or not crawl_url.startswith("https://") or not key:
        raise ValueError(
            "smoke tests require HTTPS URLs and a credential; crawl only an owned fixture"
        )
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=10) as client:
        if client.get("/live").status_code != 200:
            raise RuntimeError("liveness smoke test failed")
        ready = client.get("/ready")
        if ready.status_code != 200 or ready.headers.get("X-Release") != digest:
            raise RuntimeError("readiness or release identity smoke test failed")
        if client.get("/internal/metrics").status_code != 404:
            raise RuntimeError("internal metrics are publicly reachable")
        payload = {"urls": [crawl_url]}
        if client.post("/crawl", json=payload).status_code != 401:
            raise RuntimeError("unauthenticated submission was not rejected")
        created = client.post("/crawl", headers={"Authorization": f"Bearer {key}"}, json=payload)
        if created.status_code != 202:
            raise RuntimeError("authenticated submission failed")
        job_id = created.json()["id"]
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            response = client.get(f"/jobs/{job_id}", headers={"Authorization": f"Bearer {key}"})
            response.raise_for_status()
            job = response.json()
            if job["status"] in {"completed", "completed_with_errors"}:
                if job["success_count"] != 1 or job["failure_count"] != 0:
                    raise RuntimeError("smoke crawl failed to persist one successful record")
                return {
                    "job_id": job_id,
                    "trace_id": created.headers.get("X-Trace-ID"),
                    "status": "passed",
                }
            time.sleep(2)
    raise TimeoutError("smoke crawl did not finish")


def deploy(
    ecs: Any,
    config: dict[str, Any],
    image: str,
    output: Path,
    *,
    base_url: str,
    key: str,
    crawl_url: str,
    broken: bool = False,
) -> None:
    if not re.fullmatch(re.escape(config["repository_url"]) + r"@sha256:[a-f0-9]{64}", image):
        raise ValueError("image must be an immutable digest in the configured ECR repository")
    if not base_url.startswith("https://") or not crawl_url.startswith("https://") or not key:
        raise ValueError("configure HTTPS smoke URLs and credential before deployment")
    cluster = config["cluster"]
    names = list(config["services"].values())
    current = ecs.describe_services(cluster=cluster, services=names)
    if current.get("failures") or len(current["services"]) != len(names):
        raise RuntimeError("could not capture the current services")
    previous = {
        s["serviceName"]: {"taskDefinition": s["taskDefinition"], "desiredCount": s["desiredCount"]}
        for s in current["services"]
    }
    outcome: dict[str, Any] = {
        "started_at": datetime.now(UTC).isoformat(),
        "revision": os.getenv("GITHUB_SHA"),
        "image": image,
        "previous": previous,
        "status": "in_progress",
        "environment": "AWS",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(outcome, indent=2), encoding="utf-8")
    changed = False
    try:
        migration = register_revision(ecs, config["task_definitions"]["migration"], image)
        outcome["migration_task"] = migrate(ecs, config, migration)
        expected = {}
        for kind in ("api", "worker"):
            arn = register_revision(ecs, config["task_definitions"][kind], image, broken=broken)
            service = config["services"][kind]
            expected[service] = {
                "taskDefinition": arn,
                "desiredCount": config["desired_counts"][kind],
            }
            changed = True
            ecs.update_service(
                cluster=cluster,
                service=service,
                taskDefinition=arn,
                desiredCount=config["desired_counts"][kind],
            )
        outcome["requested"] = expected
        ecs.get_waiter("services_stable").wait(
            cluster=cluster, services=names, WaiterConfig={"Delay": 15, "MaxAttempts": 60}
        )
        verify_revisions(ecs, cluster, expected)
        if broken:
            raise RuntimeError("deliberately broken release unexpectedly became healthy")
        outcome["smoke"] = smoke(base_url, key, crawl_url, image.split("@", 1)[1])
        outcome["status"] = "passed"
    except Exception as exc:
        outcome["status"] = "failed"
        outcome["error_category"] = type(exc).__name__
        if changed:
            try:
                for service, prior in previous.items():
                    ecs.update_service(cluster=cluster, service=service, **prior)
                ecs.get_waiter("services_stable").wait(
                    cluster=cluster, services=names, WaiterConfig={"Delay": 15, "MaxAttempts": 60}
                )
                verify_revisions(ecs, cluster, previous)
                outcome["rollback"] = "verified_previous_revisions"
            except Exception as rollback_error:
                outcome["rollback"] = "failed"
                outcome["rollback_error_category"] = type(rollback_error).__name__
        raise
    finally:
        outcome["finished_at"] = datetime.now(UTC).isoformat()
        output.write_text(json.dumps(outcome, indent=2), encoding="utf-8")


def main() -> None:
    import boto3  # type: ignore[import-untyped]

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, default=Path("release-outcome.json"))
    parser.add_argument("--inject-broken-release", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    ecs = boto3.client("ecs", region_name=config["region"])
    deploy(
        ecs,
        config,
        args.image,
        args.output,
        base_url=os.environ["API_BASE_URL"],
        key=os.environ["API_KEY"],
        crawl_url=os.environ["SMOKE_CRAWL_URL"],
        broken=args.inject_broken_release,
    )


if __name__ == "__main__":
    main()
