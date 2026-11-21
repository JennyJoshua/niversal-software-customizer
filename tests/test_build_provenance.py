from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker


SCHEMA_PATH = (
    Path(__file__).parents[1]
    / "engine"
    / "customizer"
    / "schemas"
    / "build-provenance.schema.json"
)


def _schema():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def _manifest():
    digest = "a" * 64
    git_sha = "b" * 40
    return {
        "schema_version": "1.0",
        "operation": "usc_build_provenance",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "repository_url": "https://github.com/example/project",
            "commit_sha": git_sha,
            "tree_sha": "c" * 40,
            "snapshot_sha256": digest,
            "worktree_clean": True,
        },
        "upstream": None,
        "customization": {
            "project_id": "synthetic-fixture",
            "registry_sha256": None,
            "project_config_sha256": None,
            "branding_config_sha256": None,
        },
        "build": {
            "evidence_path": "evidence/build-report.json",
            "evidence_sha256": digest,
            "status": "passed",
            "command_sha256": digest,
            "image": "python:3.12-slim@sha256:" + digest,
            "docker_image_id": "sha256:" + digest,
            "source_snapshot_sha256": digest,
            "artifact_inventory_sha256": digest,
            "docker_engine_version": "27.0",
        },
        "artifacts": [
            {"path": "artifacts/app.zip", "size_bytes": 123, "sha256": digest}
        ],
        "release_authorized": False,
    }


def test_build_provenance_schema_is_valid_and_accepts_synthetic_manifest():
    validator = Draft202012Validator(_schema(), format_checker=FormatChecker())
    errors = list(validator.iter_errors(_manifest()))
    assert errors == []


@pytest.mark.parametrize(
    ("mutate", "expected_fragment"),
    [
        (lambda item: item["source"].update(commit_sha="short"), "commit_sha"),
        (lambda item: item["source"].update(repository_url="https://user:pass@example.test/repo"), "repository_url"),
        (lambda item: item.update(release_authorized=True), "release_authorized"),
        (lambda item: item["artifacts"][0].update(path="../escape.zip"), None),
        (lambda item: item["build"].update(extra_field="unexpected"), "extra_field"),
    ],
)
def test_build_provenance_schema_rejects_invalid_manifest(mutate, expected_fragment):
    manifest = _manifest()
    mutate(manifest)
    validator = Draft202012Validator(_schema(), format_checker=FormatChecker())
    errors = list(validator.iter_errors(manifest))
    assert errors
    if expected_fragment:
        assert any(expected_fragment in str(error.message) or expected_fragment in ".".join(map(str, error.path)) for error in errors)
