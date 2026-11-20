from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from customizer.configuration import validate_project_branding_configuration


ROOT = Path(__file__).resolve().parents[1]
CONFIGURATION = ROOT / "configuration"


def make_fixture(tmp_path: Path):
    project_root = tmp_path / "source"
    (project_root / "branding").mkdir(parents=True)
    (project_root / "branding" / "logo.svg").write_text("<svg/>\n", encoding="utf-8")
    (project_root / "branding" / "favicon.ico").write_bytes(b"icon")
    project_config = tmp_path / "project.json"
    branding_config = tmp_path / "branding.json"
    project = json.loads((CONFIGURATION / "project.example.json").read_text(encoding="utf-8"))
    branding = json.loads((CONFIGURATION / "branding.example.json").read_text(encoding="utf-8"))
    project_config.write_text(json.dumps(project), encoding="utf-8")
    branding_config.write_text(json.dumps(branding), encoding="utf-8")
    return project_root, project_config, branding_config, project, branding


def write_configs(project_config: Path, branding_config: Path, project: dict, branding: dict):
    project_config.write_text(json.dumps(project), encoding="utf-8")
    branding_config.write_text(json.dumps(branding), encoding="utf-8")


def test_runtime_validator_accepts_valid_configs_and_existing_assets(tmp_path):
    root, project_path, branding_path, _, _ = make_fixture(tmp_path)

    report = validate_project_branding_configuration(root, project_path, branding_path)

    assert report["status"] == "valid"
    assert report["project_id"] == "sample-web-product"
    assert report["product_name"] == "Example Product"
    assert report["assets"] == [
        {"field": "favicon_path", "path": "branding/favicon.ico", "status": "valid"},
        {"field": "logo_path", "path": "branding/logo.svg", "status": "valid"},
    ]
    assert report["read_only"] is True
    assert report["code_executed"] is False


def test_runtime_validator_blocks_schema_invalid_names_colors_and_urls(tmp_path):
    root, project_path, branding_path, project, branding = make_fixture(tmp_path)
    project["project_id"] = "../bad"
    branding["brand"]["product_name"] = "   "
    branding["visual"]["primary_color"] = "red"
    branding["brand"]["website_url"] = "http://example.com"
    write_configs(project_path, branding_path, project, branding)

    report = validate_project_branding_configuration(root, project_path, branding_path)

    assert report["status"] == "blocked"
    assert any("project_id" in error for error in report["errors"])
    assert any("product_name" in error for error in report["errors"])
    assert any("primary_color" in error for error in report["errors"])
    assert any("website_url" in error for error in report["errors"])


@pytest.mark.parametrize("asset_path", [
    "../outside.svg",
    "/etc/passwd",
    ".git/config",
    ".usc/upstream-baseline.json",
    "LICENSE",
    "docs/NOTICE.md",
    "branding/../../outside.svg",
    "branding\\logo.svg",
])
def test_runtime_validator_blocks_traversal_and_protected_asset_paths(tmp_path, asset_path):
    root, project_path, branding_path, _, branding = make_fixture(tmp_path)
    branding["visual"]["logo_path"] = asset_path
    write_configs(project_path, branding_path, json.loads(project_path.read_text()), branding)

    report = validate_project_branding_configuration(root, project_path, branding_path)

    assert report["status"] == "blocked"
    assert any("logo_path" in error for error in report["errors"])


def test_runtime_validator_blocks_missing_assets(tmp_path):
    root, project_path, branding_path, _, branding = make_fixture(tmp_path)
    branding["visual"]["logo_path"] = "branding/missing.svg"
    write_configs(project_path, branding_path, json.loads(project_path.read_text()), branding)

    report = validate_project_branding_configuration(root, project_path, branding_path)

    assert report["status"] == "blocked"
    assert any("does not resolve to an existing file" in error for error in report["errors"])


def test_runtime_validator_blocks_symlinked_assets_and_symlink_escape(tmp_path):
    root, project_path, branding_path, _, branding = make_fixture(tmp_path)
    outside = tmp_path / "outside.svg"
    outside.write_text("<svg/>\n", encoding="utf-8")
    (root / "branding" / "linked.svg").symlink_to(outside)
    branding["visual"]["logo_path"] = "branding/linked.svg"
    write_configs(project_path, branding_path, json.loads(project_path.read_text()), branding)

    report = validate_project_branding_configuration(root, project_path, branding_path)

    assert report["status"] == "blocked"
    assert any("symlink" in error for error in report["errors"])


def test_runtime_validator_rejects_symlinked_config_files_and_project_roots(tmp_path):
    root, project_path, branding_path, _, _ = make_fixture(tmp_path)
    external = tmp_path / "external.json"
    external.write_text(project_path.read_text(encoding="utf-8"), encoding="utf-8")
    linked_config = tmp_path / "linked-project.json"
    linked_config.symlink_to(external)

    report = validate_project_branding_configuration(root, linked_config, branding_path)
    assert report["status"] == "blocked"
    assert any("must not be a symlink" in error for error in report["errors"])

    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(root, target_is_directory=True)
    report = validate_project_branding_configuration(linked_root, project_path, branding_path)
    assert report["status"] == "blocked"
    assert "Project root must not be a symlink." in report["errors"]


def test_runtime_validator_rejects_duplicate_json_keys(tmp_path):
    root, project_path, branding_path, _, _ = make_fixture(tmp_path)
    project_path.write_text(
        '{"schema_version":1,"schema_version":1,"project_id":"sample-web-product"}',
        encoding="utf-8",
    )

    report = validate_project_branding_configuration(root, project_path, branding_path)

    assert report["status"] == "blocked"
    assert any("duplicate JSON object key" in error for error in report["errors"])


def test_runtime_validation_is_read_only(tmp_path):
    root, project_path, branding_path, _, _ = make_fixture(tmp_path)
    before = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*") if path.is_file() and not path.is_symlink()
    }

    report = validate_project_branding_configuration(root, project_path, branding_path)

    after = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*") if path.is_file() and not path.is_symlink()
    }
    assert report["status"] == "valid"
    assert before == after


def test_packaged_schemas_match_canonical_configuration_schemas():
    from importlib.resources import files

    for name in ("project.schema.json", "branding.schema.json"):
        packaged = json.loads(files("customizer").joinpath("schemas", name).read_text(encoding="utf-8"))
        canonical = json.loads((CONFIGURATION / name).read_text(encoding="utf-8"))
        assert packaged == canonical


def test_config_check_cli_reports_blocked_and_valid_statuses(tmp_path, capsys):
    from customizer.cli import main

    root, project_path, branding_path, _, branding = make_fixture(tmp_path)
    assert main([
        "config-check", "--path", str(root),
        "--project-config", str(project_path),
        "--branding-config", str(branding_path),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "valid"

    branding["visual"]["logo_path"] = "../outside.svg"
    write_configs(project_path, branding_path, json.loads(project_path.read_text()), branding)
    assert main([
        "config-check", "--path", str(root),
        "--project-config", str(project_path),
        "--branding-config", str(branding_path),
    ]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
