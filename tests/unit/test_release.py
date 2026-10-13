from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from atlaspipe.release import deploy, register_revision, verify_revisions


def test_waiter_success_after_automatic_rollback_is_rejected() -> None:
    ecs = Mock()
    ecs.describe_services.return_value = {
        "services": [
            {
                "serviceName": "api",
                "deployments": [
                    {"status": "PRIMARY", "taskDefinition": "old", "rolloutState": "COMPLETED"}
                ],
                "runningCount": 1,
                "pendingCount": 0,
            }
        ]
    }
    with pytest.raises(RuntimeError, match="possibly automatic rollback"):
        verify_revisions(ecs, "cluster", {"api": {"taskDefinition": "new", "desiredCount": 1}})


def test_task_registration_preserves_roles_secrets_and_pins_release() -> None:
    ecs = Mock()
    ecs.describe_task_definition.return_value = {
        "taskDefinition": {
            "family": "api",
            "revision": 99,
            "taskDefinitionArn": "old",
            "taskRoleArn": "role",
            "containerDefinitions": [
                {
                    "name": "app",
                    "image": "old",
                    "secrets": [{"name": "API_KEY", "valueFrom": "secret-arn"}],
                    "environment": [{"name": "RELEASE", "value": "old"}],
                }
            ],
        }
    }
    ecs.register_task_definition.return_value = {"taskDefinition": {"taskDefinitionArn": "new"}}
    assert register_revision(ecs, "old", "repo@sha256:abc") == "new"
    payload = ecs.register_task_definition.call_args.kwargs
    assert "revision" not in payload
    assert payload["taskRoleArn"] == "role"
    assert payload["containerDefinitions"][0]["secrets"][0]["valueFrom"] == "secret-arn"
    assert payload["containerDefinitions"][0]["environment"] == [
        {"name": "RELEASE", "value": "sha256:abc"}
    ]


def test_failed_smoke_restores_both_services_and_records_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ecs = Mock()
    old = {
        "api": {"taskDefinition": "old-api", "desiredCount": 1},
        "worker": {"taskDefinition": "old-worker", "desiredCount": 2},
    }
    ecs.describe_services.return_value = {
        "services": [{"serviceName": name, **prior} for name, prior in old.items()]
    }
    monkeypatch.setattr(
        "atlaspipe.release.register_revision", lambda _ecs, arn, _image, **_kw: "new-" + arn
    )
    monkeypatch.setattr("atlaspipe.release.migrate", lambda *_args: "migration-task")
    verify = Mock()
    monkeypatch.setattr("atlaspipe.release.verify_revisions", verify)
    monkeypatch.setattr(
        "atlaspipe.release.smoke", Mock(side_effect=RuntimeError("fixture smoke failure"))
    )
    config = {
        "cluster": "cluster",
        "repository_url": "repo",
        "services": {"api": "api", "worker": "worker"},
        "task_definitions": {"api": "api", "worker": "worker", "migration": "migration"},
        "desired_counts": {"api": 1, "worker": 2},
    }
    output = tmp_path / "release.json"
    with pytest.raises(RuntimeError, match="fixture smoke failure"):
        deploy(
            ecs,
            config,
            "repo@sha256:" + "a" * 64,
            output,
            base_url="https://api.example",
            key="fixture",
            crawl_url="https://owned.example",
        )
    calls = ecs.update_service.call_args_list
    assert calls[-2].kwargs == {"cluster": "cluster", "service": "api", **old["api"]}
    assert calls[-1].kwargs == {"cluster": "cluster", "service": "worker", **old["worker"]}
    assert verify.call_args.args[2] == old
    result = json.loads(output.read_text())
    assert result["status"] == "failed"
    assert result["rollback"] == "verified_previous_revisions"
    assert "fixture smoke failure" not in output.read_text()
