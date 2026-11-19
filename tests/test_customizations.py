from __future__ import annotations

import json
from pathlib import Path

from customizer.customizations import inspect_customization_registry


def write_registry(root: Path, data: dict) -> Path:
    directory = root / ".usc"
    directory.mkdir(parents=True, exist_ok=True)
    registry = directory / "customizations.json"
    registry.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return registry


def make_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "branding.json").write_text('{"brand":"custom"}\n', encoding="utf-8")
    (root / "src" / "checkout.py").write_text("def checkout(): return 'custom'\n", encoding="utf-8")
    return root


def valid_registry() -> dict:
    return {
        "schema_version": "1.0",
        "project_id": "example-product",
        "customizations": [
            {
                "id": "custom-branding",
                "name": "Product branding",
                "purpose": "Keep the customized product identity.",
                "category": "branding",
                "protection_mode": "preserve",
                "paths": [{"path": "src/branding.json", "ownership": "custom_only"}],
            },
            {
                "id": "checkout-business-rule",
                "name": "Checkout business rule",
                "purpose": "Preserve the custom checkout validation behaviour.",
                "category": "business_rule",
                "protection_mode": "require_regression_tests",
                "paths": [{"path": "src/checkout.py", "ownership": "mixed"}],
                "test_ids": ["test_checkout_validation"],
                "evidence_refs": ["https://github.com/example/product/actions/runs/123"],
            },
        ],
    }


def test_missing_registry_is_not_configured_and_does_not_block_existing_projects(tmp_path):
    root = make_project(tmp_path)

    report = inspect_customization_registry(root)

    assert report["status"] == "not_configured"
    assert report["customization_count"] == 0
    assert report["feature_protection_enforced"] is False
    assert not (root / ".usc").exists()


def test_valid_registry_reports_feature_declarations_without_claiming_enforcement(tmp_path):
    root = make_project(tmp_path)
    write_registry(root, valid_registry())

    report = inspect_customization_registry(root)

    assert report["status"] == "valid"
    assert report["customization_count"] == 2
    assert report["feature_protection_enforced"] is False
    assert report["entries"][1]["paths"] == [{"path": "src/checkout.py", "ownership": "mixed"}]
    assert report["entries"][1]["test_ids"] == ["test_checkout_validation"]
    assert report["errors"] == []


def test_registry_rejects_duplicate_ids_and_unsupported_fields(tmp_path):
    root = make_project(tmp_path)
    data = valid_registry()
    data["customizations"][1]["id"] = "custom-branding"
    data["customizations"][1]["unexpected"] = True
    write_registry(root, data)

    report = inspect_customization_registry(root)

    assert report["status"] == "blocked"
    assert any("Duplicate customization id" in error for error in report["errors"])
    assert any("unsupported field" in error for error in report["errors"])


def test_registry_rejects_stale_paths_and_path_traversal(tmp_path):
    root = make_project(tmp_path)
    data = valid_registry()
    data["customizations"][0]["paths"][0]["path"] = "src/missing.py"
    data["customizations"][1]["paths"][0]["path"] = "../outside.py"
    write_registry(root, data)

    report = inspect_customization_registry(root)

    assert report["status"] == "blocked"
    assert any("missing or stale file" in error for error in report["errors"])
    assert any("safe repository-relative path" in error for error in report["errors"])


def test_registry_rejects_globs_and_mixed_ownership_preserve_mode(tmp_path):
    root = make_project(tmp_path)
    data = valid_registry()
    data["customizations"][0]["paths"][0]["path"] = "src/*.json"
    data["customizations"][1]["protection_mode"] = "preserve"
    write_registry(root, data)

    report = inspect_customization_registry(root)

    assert report["status"] == "blocked"
    assert any("globs" in error for error in report["errors"])
    assert any("mixed-ownership file" in error for error in report["errors"])


def test_registry_requires_test_ids_for_regression_mode_and_review_note_for_block_mode(tmp_path):
    root = make_project(tmp_path)
    data = valid_registry()
    data["customizations"][1]["test_ids"] = []
    data["customizations"][0]["protection_mode"] = "block_for_review"
    write_registry(root, data)

    report = inspect_customization_registry(root)

    assert report["status"] == "blocked"
    assert any("requires at least one test_id" in error for error in report["errors"])
    assert any("requires a review_note" in error for error in report["errors"])


def test_registry_rejects_inconsistent_ownership_for_shared_path(tmp_path):
    root = make_project(tmp_path)
    data = valid_registry()
    data["customizations"].append({
        "id": "checkout-configuration",
        "name": "Checkout configuration",
        "purpose": "Protect the checkout configuration.",
        "category": "configuration",
        "protection_mode": "preserve",
        "paths": [{"path": "src/checkout.py", "ownership": "custom_only"}],
    })
    write_registry(root, data)

    report = inspect_customization_registry(root)

    assert report["status"] == "blocked"
    assert any("inconsistent ownership" in error for error in report["errors"])


def test_registry_rejects_symlinked_feature_paths(tmp_path):
    root = make_project(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("outside\n", encoding="utf-8")
    (root / "src" / "linked.py").symlink_to(outside)
    data = valid_registry()
    data["customizations"][0]["paths"][0]["path"] = "src/linked.py"
    write_registry(root, data)

    report = inspect_customization_registry(root)

    assert report["status"] == "blocked"
    assert any("symlink" in error for error in report["errors"])


def test_registry_file_and_metadata_directory_must_not_be_symlinks(tmp_path):
    root = make_project(tmp_path)
    external_registry = tmp_path / "registry.json"
    external_registry.write_text(json.dumps(valid_registry()), encoding="utf-8")
    (root / ".usc").mkdir()
    (root / ".usc" / "customizations.json").symlink_to(external_registry)

    report = inspect_customization_registry(root)

    assert report["status"] == "blocked"
    assert any("registry file must not be a symlink" in error for error in report["errors"])


def test_registry_rejects_evidence_urls_that_may_contain_credentials_or_tokens(tmp_path):
    root = make_project(tmp_path)
    data = valid_registry()
    data["customizations"][1]["evidence_refs"] = [
        "https://user:password@example.com/run",
        "https://example.com/run?token=secret",
    ]
    write_registry(root, data)

    report = inspect_customization_registry(root)

    assert report["status"] == "blocked"
    assert any("credential-free HTTPS URL" in error for error in report["errors"])


def test_registry_cli_exit_codes_distinguish_valid_missing_and_blocked(tmp_path, capsys):
    from customizer.cli import main

    root = make_project(tmp_path)
    assert main(["customization-check", "--path", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "not_configured"

    write_registry(root, valid_registry())
    assert main(["customization-check", "--path", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "valid"

    data = valid_registry()
    data["schema_version"] = "2.0"
    write_registry(root, data)
    assert main(["customization-check", "--path", str(root)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
