from __future__ import annotations

import json
import shutil
from pathlib import Path

from customizer.web_nextjs import apply_nextjs_branding, create_nextjs_branding_plan


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "nextjs-app-router"
ICO_BYTES = bytes.fromhex("0000010001000101000001002000040000001600000000000000")


def project_fixture(tmp_path: Path, *, review_status: str = "approved") -> tuple[Path, Path, Path]:
    source = tmp_path / "source"
    shutil.copytree(FIXTURE, source)
    (source / "branding" / "favicon.ico").write_bytes(ICO_BYTES)
    project = {
        "schema_version": 1,
        "project_id": "fixture-nextjs",
        "source": {"repository_url": "https://github.com/example/fixture", "revision": "v1.0.0"},
        "adapter": "web-nextjs",
        "licence_review": {
            "status": review_status,
            "review_record": {
                "reviewer": "Fixture reviewer",
                "reviewed_at": "2026-11-21T00:00:00Z",
                "evidence_url": "https://example.com/licence-review",
            } if review_status == "approved" else None,
        },
    }
    branding = {
        "schema_version": 1,
        "brand": {
            "product_name": "My PNG Product",
            "publisher_name": "Example Publisher",
            "tagline": "A locally customized product",
        },
        "visual": {
            "primary_color": "#123456",
            "secondary_color": "#ABCDEF",
            "logo_path": "branding/logo.svg",
            "favicon_path": "branding/favicon.ico",
        },
    }
    project_path = tmp_path / "project.json"
    branding_path = tmp_path / "branding.json"
    project_path.write_text(json.dumps(project), encoding="utf-8")
    branding_path.write_text(json.dumps(branding), encoding="utf-8")
    return source, project_path, branding_path


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*") if path.is_file()
    }


def test_nextjs_plan_is_deterministic_read_only_and_allowlisted(tmp_path):
    source, project, branding = project_fixture(tmp_path)
    before = snapshot(source)

    first = create_nextjs_branding_plan(source, project, branding)
    second = create_nextjs_branding_plan(source, project, branding)

    assert first == second
    assert first["status"] == "ready_for_review"
    assert first["read_only"] is True
    assert first["files_changed"] is False
    assert first["code_executed"] is False
    assert first["write_allowlist"] == [
        "app/globals.css", "app/layout.tsx", "app/page.tsx",
        "public/usc-brand-favicon.ico", "public/usc-brand-logo.svg",
    ]
    assert set(first["write_allowlist"]).issubset({
        "app/layout.tsx", "app/globals.css", "app/page.tsx",
        "src/app/layout.tsx", "src/app/globals.css", "src/app/page.tsx",
        "public/usc-brand-logo.svg", "public/usc-brand-favicon.ico",
    })
    assert snapshot(source) == before


def test_apply_requires_explicit_approval_and_human_licence_review(tmp_path):
    source, project, branding = project_fixture(tmp_path)
    before = snapshot(source)

    denied = apply_nextjs_branding(source, project, branding, approved=False)
    assert denied["status"] == "blocked_approval_required"
    assert snapshot(source) == before

    source2, project2, branding2 = project_fixture(tmp_path / "pending", review_status="pending")
    denied_review = apply_nextjs_branding(source2, project2, branding2, approved=True)
    assert denied_review["status"] == "blocked_unsafe_or_unsupported"
    assert snapshot(source2) == snapshot(source2)


def test_apply_changes_only_allowlisted_branding_surfaces(tmp_path):
    source, project, branding = project_fixture(tmp_path)
    before = snapshot(source)

    report = apply_nextjs_branding(source, project, branding, approved=True)

    assert report["status"] == "applied"
    assert report["files_changed"] is True
    assert report["code_executed"] is False
    assert {item["path"] for item in report["changed_files"]} == {
        "app/globals.css", "app/layout.tsx", "app/page.tsx",
        "public/usc-brand-favicon.ico", "public/usc-brand-logo.svg",
    }
    assert "My PNG Product" in (source / "app" / "layout.tsx").read_text(encoding="utf-8")
    assert "A locally customized product" in (source / "app" / "layout.tsx").read_text(encoding="utf-8")
    assert "--usc-primary: #123456" in (source / "app" / "globals.css").read_text(encoding="utf-8")
    assert "alt=\\"My PNG Product\\"" in (source / "app" / "page.tsx").read_text(encoding="utf-8")
    after = snapshot(source)
    changed = {path for path in before if before[path] != after[path]}
    assert changed == {
        "app/globals.css", "app/layout.tsx", "app/page.tsx",
        "public/usc-brand-favicon.ico", "public/usc-brand-logo.svg",
    }
    assert (source / "LICENSE").read_bytes() == before["LICENSE"]
    assert (source / "package.json").read_bytes() == before["package.json"]


def test_adapter_refuses_to_overwrite_existing_public_asset(tmp_path):
    source, project, branding = project_fixture(tmp_path)
    target = source / "public" / "usc-brand-logo.svg"
    target.write_text("<svg><text>user file</text></svg>", encoding="utf-8")
    before = snapshot(source)

    report = create_nextjs_branding_plan(source, project, branding)

    assert report["status"] == "blocked_unsafe_or_unsupported"
    assert snapshot(source) == before


def test_adapter_rejects_unsafe_svg_before_planning_or_writing(tmp_path):
    source, project, branding = project_fixture(tmp_path)
    (source / "branding" / "logo.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        encoding="utf-8",
    )
    before = snapshot(source)

    report = apply_nextjs_branding(source, project, branding, approved=True)

    assert report["status"] == "blocked_unsafe_or_unsupported"
    assert snapshot(source) == before


def test_adapter_rejects_missing_or_duplicate_markers(tmp_path):
    source, project, branding = project_fixture(tmp_path)
    page = source / "app" / "page.tsx"
    page.write_text("export default function Page() { return <main /> }", encoding="utf-8")
    before = snapshot(source)

    report = create_nextjs_branding_plan(source, project, branding)

    assert report["status"] == "blocked_unsafe_or_unsupported"
    assert snapshot(source) == before


def test_adapter_rejects_symlinked_brand_asset(tmp_path):
    source, project, branding = project_fixture(tmp_path)
    outside = tmp_path / "outside.svg"
    outside.write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8")
    (source / "branding" / "logo.svg").unlink()
    (source / "branding" / "logo.svg").symlink_to(outside)
    before = snapshot(source)

    report = create_nextjs_branding_plan(source, project, branding)

    assert report["status"] in {"blocked_invalid_configuration", "blocked_unsafe_or_unsupported"}
    assert snapshot(source) == before
