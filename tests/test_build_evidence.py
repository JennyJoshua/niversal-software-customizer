from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from customizer.build_evidence import (
    create_artifact_inventory,
    redact_build_logs,
    validate_build_evidence,
)


def test_log_redaction_masks_common_secrets_and_authenticated_urls():
    raw = (
        "token=supersecret password: hunter2 "
        "Authorization: Bearer abc.def.ghi "
        "https://user:pass@example.test/path "
        "ghp_" + "A" * 32
    )
    result = redact_build_logs(raw)
    assert "supersecret" not in result
    assert "hunter2" not in result
    assert "abc.def.ghi" not in result
    assert "user:pass" not in result
    assert "ghp_" + "A" * 32 not in result
    assert "[REDACTED]" in result


def test_artifact_inventory_is_deterministic_and_hashes_file_content(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    (output / "app").mkdir()
    payload = b"synthetic artifact"
    (output / "app" / "bundle.bin").write_bytes(payload)

    first, first_hash = create_artifact_inventory(output)
    second, second_hash = create_artifact_inventory(output)

    assert first == second
    assert first_hash == second_hash
    assert first[0]["path"] == "app/bundle.bin"
    assert first[0]["sha256"] == hashlib.sha256(payload).hexdigest()


def test_artifact_inventory_rejects_symlinks(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (output / "linked.txt").symlink_to(outside)

    with pytest.raises(ValueError, match="symlinked file"):
        create_artifact_inventory(output)


def test_evidence_schema_rejects_unexpected_fields():
    with pytest.raises(ValueError, match="unexpected"):
        validate_build_evidence({
            "schema_version": "1.0",
            "operation": "isolated_build",
            "status": "passed",
            "executed": True,
            "unexpected": "not allowed",
        })
