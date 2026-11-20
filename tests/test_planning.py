from __future__ import annotations

import json
from pathlib import Path

from customizer.planning import create_customization_dry_run, detect_adapters


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configuration"


def fixture(tmp_path: Path):
    source = tmp_path / "source"
    (source / "branding").mkdir(parents=True)
    (source / "branding" / "logo.svg").write_text("<svg/>", encoding="utf-8")
    (source / "branding" / "favicon.ico").write_bytes(b"icon")
    (source / "package.json").write_text(
        json.dumps({"name": "sample", "dependencies": {"next": "15", "react": "19"}}),
        encoding="utf-8",
    )
    project = tmp_path / "project.json"
    branding = tmp_path / "branding.json"
    project.write_text((CONFIG / "project.example.json").read_text(encoding="utf-8"), encoding="utf-8")
    branding.write_text((CONFIG / "branding.example.json").read_text(encoding="utf-8"), encoding="utf-8")
    return source, project, branding


def test_adapter_detection_is_deterministic_and_never_executes_source(tmp_path):
    source, _, _ = fixture(tmp_path)
    first = detect_adapters(source)
    second = detect_adapters(source)

    assert first == second
    assert first["status"] == "candidates_detected"
    assert first["technology_families"] == ["nextjs", "react"]
    assert first["candidates"] == [
        {"adapter_id": "web-nextjs", "technology_family": "nextjs", "status": "detected_not_implemented"},
        {"adapter_id": "web-react", "technology_family": "react", "status": "detected_not_implemented"},
    ]
    assert first["read_only"] is True
    assert first["code_executed"] is False


def test_dry_run_reports_candidate_but_does_not_claim_unimplemented_adapter(tmp_path):
    source, project, branding = fixture(tmp_path)
    before = {
        path.relative_to(source).as_posix(): path.read_bytes()
        for path in source.rglob("*") if path.is_file()
    }

    first = create_customization_dry_run(source, project, branding)
    second = create_customization_dry_run(source, project, branding)
    after = {
        path.relative_to(source).as_posix(): path.read_bytes()
        for path in source.rglob("*") if path.is_file()
    }

    assert first == second
    assert first["status"] == "adapter_not_implemented"
    assert first["configured_adapter"] == "web"
    assert first["detected_candidates"] == ["web-nextjs", "web-react"]
    assert first["requested_fields"] == [
        "brand.product_name", "brand.publisher_name", "brand.support_url",
        "brand.tagline", "brand.website_url", "visual.favicon_path",
        "visual.primary_color", "visual.secondary_color", "visual.logo_path",
    ]
    assert first["planned_changes"] == []
    assert first["unsupported_fields"] == first["requested_fields"]
    assert first["read_only"] is True
    assert first["files_changed"] is False
    assert before == after


def test_dry_run_blocks_invalid_configuration(tmp_path):
    source, project, branding = fixture(tmp_path)
    invalid = json.loads(branding.read_text(encoding="utf-8"))
    invalid["visual"]["logo_path"] = "../outside.svg"
    branding.write_text(json.dumps(invalid), encoding="utf-8")

    report = create_customization_dry_run(source, project, branding)

    assert report["status"] == "blocked_invalid_configuration"
    assert report["planned_changes"] == []
    assert report["files_changed"] is False
    assert any("logo_path" in error for error in report["errors"])


def test_dry_run_blocks_adapter_mismatch(tmp_path):
    source, project, branding = fixture(tmp_path)
    data = json.loads(project.read_text(encoding="utf-8"))
    data["adapter"] = "python"
    project.write_text(json.dumps(data), encoding="utf-8")

    report = create_customization_dry_run(source, project, branding)

    assert report["status"] == "blocked_adapter_mismatch"
    assert report["planned_changes"] == []
    assert any("does not match detected candidates" in error for error in report["errors"])
