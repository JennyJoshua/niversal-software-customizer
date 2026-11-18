import json
from pathlib import Path

from customizer.licensing import scan_licence_evidence


def test_finds_root_and_nested_rights_files_and_spdx(tmp_path: Path):
    (tmp_path / "LICENSE").write_text("SPDX-License-Identifier: MIT\n", encoding="utf-8")
    nested = tmp_path / "third_party" / "component"
    nested.mkdir(parents=True)
    (nested / "COPYING").write_text("SPDX-License-Identifier: Apache-2.0\n", encoding="utf-8")
    (tmp_path / "NOTICE").write_text("Upstream notices", encoding="utf-8")
    report = scan_licence_evidence(tmp_path)
    assert [item["path"] for item in report["project_licence"]["root_evidence_files"]] == ["LICENSE"]
    assert [item["path"] for item in report["project_licence"]["nested_evidence_files"]] == [
        "third_party/component/COPYING"
    ]
    assert report["project_licence"]["spdx_identifiers_found"] == ["MIT"]
    assert report["review_status"] == "human_review_required"
    assert report["customization_gate"] == "blocked"
    assert report["legal_approval"] is False


def test_missing_root_licence_blocks_even_when_nested_licence_exists(tmp_path: Path):
    nested = tmp_path / "vendor" / "library"
    nested.mkdir(parents=True)
    (nested / "LICENSE").write_text("Library licence", encoding="utf-8")
    report = scan_licence_evidence(tmp_path)
    assert report["project_licence"]["missing_root_licence_evidence"] is True
    assert report["customization_gate"] == "blocked"
    assert report["project_licence"]["nested_evidence_files"][0]["path"] == "vendor/library/LICENSE"


def test_detects_conflicting_project_licence_signals(tmp_path: Path):
    (tmp_path / "LICENSE").write_text("SPDX-License-Identifier: MIT\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "sample", "license": "Apache-2.0",
        "dependencies": {"react": "^18.0.0"},
    }), encoding="utf-8")
    report = scan_licence_evidence(tmp_path)
    assert report["project_licence"]["conflicts"]
    assert report["customization_gate"] == "blocked"
    assert report["dependencies"]["items"][0]["name"] == "react"


def test_extracts_supported_dependency_declarations(tmp_path: Path):
    (tmp_path / "package.json").write_text(json.dumps({
        "dependencies": {"react": "^18", "zod": "^3"},
        "devDependencies": {"vitest": "^1"},
    }), encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("requests>=2\n# comment\nflask==3\n", encoding="utf-8")
    report = scan_licence_evidence(tmp_path)
    names = {item["name"] for item in report["dependencies"]["items"]}
    assert {"react", "zod", "vitest", "requests", "flask"} <= names
    assert report["dependencies"]["licence_status"] == "not_resolved"


def test_detects_asset_font_dataset_and_logo_review_hints(tmp_path: Path):
    for directory in ("assets", "fonts", "datasets", "logos"):
        (tmp_path / directory).mkdir()
        (tmp_path / directory / "sample.bin").write_bytes(b"x")
    report = scan_licence_evidence(tmp_path)
    categories = report["other_rights_evidence"]["assets_fonts_data_and_trademarks"]["detected_categories"]
    assert {"asset", "font", "dataset", "logo_or_trademark"} <= set(categories)
    assert report["other_rights_evidence"]["assets_fonts_data_and_trademarks"]["trademark_review_required"]


def test_unlicensed_project_is_never_approved(tmp_path: Path):
    report = scan_licence_evidence(tmp_path)
    assert report["project_licence"]["missing_root_licence_evidence"] is True
    assert report["review_record"]["decision"] == "pending_human_review"
    assert report["legal_approval"] is False
    assert report["customization_gate"] == "blocked"



def test_recognizes_common_licence_notice_and_attribution_filenames(tmp_path: Path):
    filenames = [
        "LICENCE.txt", "COPYING.LESSER", "NOTICE.md", "AUTHORS.md",
        "COPYRIGHT", "ATTRIBUTION.md", "THIRD-PARTY-NOTICES.txt",
    ]
    for filename in filenames:
        (tmp_path / filename).write_text("Evidence for human review", encoding="utf-8")
    report = scan_licence_evidence(tmp_path)
    paths = {
        item["path"]
        for item in report["other_rights_evidence"]["root_notice_author_authorship_files"]
    }
    paths.update(item["path"] for item in report["project_licence"]["root_evidence_files"])
    assert set(filenames) <= paths


def test_reads_project_licence_declaration_from_package_metadata(tmp_path: Path):
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "declared-project", "license": "MIT",
    }), encoding="utf-8")
    report = scan_licence_evidence(tmp_path)
    assert report["project_licence"]["manifest_declarations"] == [
        {"manifest": "package.json", "expression": "MIT"}
    ]
    assert report["project_licence"]["missing_root_licence_evidence"] is False
    assert report["customization_gate"] == "blocked"
