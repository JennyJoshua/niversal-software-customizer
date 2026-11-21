"""Guarded branding adapter for explicitly marked Next.js App Router projects."""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import stat
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from typing import Any

from .configuration import validate_project_branding_configuration
from .inspector import InspectionError, inspect_repository

MAX_FILE_BYTES = 2_000_000
_ALLOWED_APP_FILES = {"layout.tsx", "globals.css", "page.tsx"}
_ALLOWED_PUBLIC_OUTPUTS = {"usc-brand-logo.svg", "usc-brand-favicon.ico"}
_MARKERS = {
    "metadata": ("/* USC:branding:metadata:start */", "/* USC:branding:metadata:end */"),
    "theme": ("/* USC:branding:theme:start */", "/* USC:branding:theme:end */"),
    "logo": ("{/* USC:branding:logo:start */}", "{/* USC:branding:logo:end */}"),
}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _unified_diff(relative: str, original: bytes | None, updated: bytes) -> tuple[str | None, str]:
    """Return a deterministic text diff; binary or oversized content is explicitly marked."""
    old_bytes = original or b""
    if b"\\x00" in old_bytes or b"\\x00" in updated:
        return None, "binary"
    try:
        old_text = old_bytes.decode("utf-8")
        new_text = updated.decode("utf-8")
    except UnicodeDecodeError:
        return None, "binary"
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = "".join(difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{relative}" if original is not None else "/dev/null",
        tofile=f"b/{relative}",
        lineterm="\n",
    ))
    if len(diff.encode("utf-8")) > 200_000:
        return None, "omitted_size_limit"
    return diff, "text"


def _load_json(path: str | Path) -> dict[str, Any]:
    supplied = Path(path).expanduser()
    if supplied.is_symlink():
        raise ValueError(f"Configuration file must not be a symlink: {supplied}")
    resolved = supplied.resolve(strict=True)
    if not resolved.is_file() or resolved.stat().st_size > 1_000_000:
        raise ValueError(f"Configuration file must be a regular file within the 1 MB limit: {supplied}")
    value = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Configuration root must be a JSON object.")
    return value


def _safe_existing_file(root: Path, relative: str) -> tuple[Path, bytes]:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"Unsafe repository-relative path: {relative}")
    current = root
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Symlink paths are not allowed: {relative}")
    resolved = current.resolve(strict=True)
    resolved.relative_to(root)
    if not resolved.is_file() or resolved.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"Path is not a regular file within the size limit: {relative}")
    return resolved, resolved.read_bytes()


def _safe_target(root: Path, relative: str) -> tuple[Path, bytes | None]:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"Unsafe target path: {relative}")
    current = root
    for part in pure.parts[:-1]:
        current = current / part
        if current.is_symlink() or not current.is_dir():
            raise ValueError(f"Target parent is missing or unsafe: {relative}")
    target = current / pure.parts[-1]
    if target.is_symlink():
        raise ValueError(f"Target is a symlink: {relative}")
    if not target.exists():
        return target, None
    resolved = target.resolve(strict=True)
    resolved.relative_to(root)
    if not resolved.is_file() or resolved.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"Target is not a regular file within the size limit: {relative}")
    return resolved, resolved.read_bytes()


def _replace_marked_block(text: str, marker_pair: tuple[str, str], replacement: str, label: str) -> str:
    start_marker, end_marker = marker_pair
    if text.count(start_marker) != 1 or text.count(end_marker) != 1:
        raise ValueError(f"{label} requires exactly one matching USC start and end marker.")
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker)
    if end <= start:
        raise ValueError(f"{label} markers are reversed or overlapping.")
    return text[:start] + "\n" + replacement.rstrip() + "\n" + text[end:]


def _validate_svg(data: bytes) -> None:
    if len(data) > 500_000:
        raise ValueError("Logo SVG exceeds the 500 KB limit.")
    upper_data = data.upper()
    if b"<!DOCTYPE" in upper_data or b"<!ENTITY" in upper_data:
        raise ValueError("Logo SVG document types and entity declarations are not allowed.")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError("Logo asset must be well-formed SVG.") from exc
    if root.tag.rsplit("}", 1)[-1].lower() != "svg":
        raise ValueError("Logo asset root element must be svg.")
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1].lower()
        if tag in {"script", "foreignobject"}:
            raise ValueError("Logo SVG contains an unsafe element.")
        text_content = (element.text or "").lower()
        if "@import" in text_content:
            raise ValueError("Logo SVG stylesheet imports are not allowed.")
        for reference in re.findall(r"url\(\s*['\"]?([^'\")]+)", text_content):
            if not reference.strip().startswith("#"):
                raise ValueError("Logo SVG external style references are not allowed.")
        for key, value in element.attrib.items():
            name = key.rsplit("}", 1)[-1].lower()
            lowered = value.strip().lower()
            if name.startswith("on"):
                raise ValueError("Logo SVG contains an event-handler attribute.")
            if name in {"href", "src"} and lowered and not lowered.startswith("#"):
                raise ValueError("Logo SVG external references are not allowed.")
            if "url(" in lowered and not re.search(r"url\(\s*#[^)]+\)", lowered):
                raise ValueError("Logo SVG external style references are not allowed.")


def _build_plan(
    project_root: str | Path,
    project_config: str | Path,
    branding_config: str | Path,
) -> tuple[dict[str, Any], dict[str, tuple[Path, bytes, bytes | None]]]:
    root_arg = Path(project_root).expanduser()
    if root_arg.is_symlink():
        raise ValueError("Project root must not be a symlink.")
    root = root_arg.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Project root must be an existing directory.")

    validation = validate_project_branding_configuration(root, project_config, branding_config)
    errors = list(validation.get("errors", []))
    if validation.get("status") != "valid":
        return ({
            "schema_version": "1.0", "operation": "customization_dry_run",
            "adapter_id": "web-nextjs", "status": "blocked_invalid_configuration",
            "planned_changes": [], "unsupported_fields": [], "errors": sorted(set(errors)),
            "read_only": True, "files_changed": False, "code_executed": False,
        }, {})

    project = _load_json(project_config)
    branding = _load_json(branding_config)
    if project.get("adapter") != "web-nextjs":
        errors.append("Project configuration adapter must be exactly 'web-nextjs'.")
    inspection = inspect_repository(root)
    if "nextjs" not in inspection.get("technology", {}).get("families", []):
        errors.append("Repository does not contain the static Next.js metadata signals required by this adapter.")

    app_candidates = []
    for prefix in ("app", "src/app"):
        app_dir = root / prefix
        if app_dir.is_symlink():
            errors.append(f"Application directory is a symlink: {prefix}")
            continue
        if app_dir.is_dir() and all((app_dir / name).is_file() for name in _ALLOWED_APP_FILES):
            app_candidates.append(prefix)
    if len(app_candidates) != 1:
        errors.append("Exactly one supported App Router layout is required: app/ or src/app/, containing layout.tsx, globals.css, and page.tsx.")
    if errors:
        return ({
            "schema_version": "1.0", "operation": "customization_dry_run",
            "adapter_id": "web-nextjs", "status": "blocked_unsupported_project",
            "planned_changes": [], "unsupported_fields": [], "errors": sorted(set(errors)),
            "read_only": True, "files_changed": False, "code_executed": False,
        }, {})

    app_prefix = app_candidates[0]
    brand = branding.get("brand", {})
    visual = branding.get("visual", {})
    product_name = brand["product_name"]
    tagline = brand.get("tagline", "")
    metadata_path = f"{app_prefix}/layout.tsx"
    css_path = f"{app_prefix}/globals.css"
    page_path = f"{app_prefix}/page.tsx"

    _, metadata_bytes = _safe_existing_file(root, metadata_path)
    _, css_bytes = _safe_existing_file(root, css_path)
    _, page_bytes = _safe_existing_file(root, page_path)
    try:
        metadata_text = metadata_bytes.decode("utf-8")
        css_text = css_bytes.decode("utf-8")
        page_text = page_bytes.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("Supported App Router files must be UTF-8 text.") from exc

    favicon_path = visual.get("favicon_path")
    logo_path = visual.get("logo_path")
    metadata_lines = [
        "export const metadata = {",
        f"  title: {json.dumps(product_name, ensure_ascii=False)},",
        f"  description: {json.dumps(tagline, ensure_ascii=False)},",
    ]
    if favicon_path:
        metadata_lines.append('  icons: { icon: "/usc-brand-favicon.ico" },')
    metadata_lines.append("};")
    next_metadata = _replace_marked_block(
        metadata_text, _MARKERS["metadata"], "\n".join(metadata_lines), metadata_path,
    )

    primary = visual.get("primary_color")
    secondary = visual.get("secondary_color")
    if bool(primary) != bool(secondary):
        raise ValueError("Next.js theme application requires both primary_color and secondary_color.")
    next_css = css_text
    if primary and secondary:
        theme = "\n".join([
            ":root {",
            f"  --usc-primary: {primary};",
            f"  --usc-secondary: {secondary};",
            "}",
        ])
        next_css = _replace_marked_block(css_text, _MARKERS["theme"], theme, css_path)

    next_page = page_text
    if logo_path:
        logo_markup = (
            '<div className="usc-brand-logo">'
            '<img src="/usc-brand-logo.svg" alt=' + json.dumps(product_name, ensure_ascii=False) +
            ' /></div>'
        )
        next_page = _replace_marked_block(page_text, _MARKERS["logo"], logo_markup, page_path)

    payloads: dict[str, tuple[Path, bytes, bytes | None]] = {}
    for relative, original, updated in (
        (metadata_path, metadata_bytes, next_metadata.encode("utf-8")),
        (css_path, css_bytes, next_css.encode("utf-8")),
        (page_path, page_bytes, next_page.encode("utf-8")),
    ):
        if original != updated:
            payloads[relative] = (root / relative, updated, original)

    for field, source_value, target_name in (
        ("logo_path", logo_path, "usc-brand-logo.svg"),
        ("favicon_path", favicon_path, "usc-brand-favicon.ico"),
    ):
        if not source_value:
            continue
        source_entry = next((item for item in validation.get("assets", []) if item["field"] == field), None)
        if source_entry is None:
            raise ValueError(f"Validated source asset is missing from report: {field}")
        source_file, source_bytes = _safe_existing_file(root, source_entry["path"])
        if field == "logo_path":
            if Path(source_entry["path"]).suffix.lower() != ".svg":
                raise ValueError("logo_path must reference an SVG file.")
            _validate_svg(source_bytes)
        else:
            if Path(source_entry["path"]).suffix.lower() != ".ico" or len(source_bytes) < 6 or source_bytes[:4] != b"\x00\x00\x01\x00":
                raise ValueError("favicon_path must reference a valid ICO file.")
        target_relative = f"public/{target_name}"
        if target_name not in _ALLOWED_PUBLIC_OUTPUTS:
            raise ValueError("Adapter attempted to write outside its public asset allowlist.")
        target_file, existing = _safe_target(root, target_relative)
        if existing is not None and existing != source_bytes:
            raise ValueError(f"Refusing to overwrite an existing non-USC asset: {target_relative}")
        if existing != source_bytes:
            payloads[target_relative] = (target_file, source_bytes, None)

    supported_fields = {
        "brand.product_name", "brand.tagline",
        "visual.primary_color", "visual.secondary_color",
        "visual.logo_path", "visual.favicon_path",
    }
    requested_fields = (
        [f"brand.{key}" for key in brand]
        + [f"visual.{key}" for key in visual]
        + [f"text_overrides.{key}" for key in branding.get("text_overrides", {})]
    )
    unsupported_fields = sorted(set(requested_fields) - supported_fields)

    operations = []
    for relative in sorted(payloads):
        _, updated, original = payloads[relative]
        diff, diff_format = _unified_diff(relative, original, updated)
        operations.append({
            "path": relative,
            "operation": "create" if original is None else "update_marked_block",
            "before_sha256": _digest(original) if original is not None else None,
            "after_sha256": _digest(updated),
            "reason": "Explicitly allowlisted Next.js branding surface or USC-owned asset target.",
            "diff": diff,
            "diff_format": diff_format,
        })
    report = {
        "schema_version": "1.0",
        "operation": "customization_dry_run",
        "adapter_id": "web-nextjs",
        "status": "ready_for_review" if operations else "no_changes_needed",
        "project_id": project.get("project_id"),
        "product_name": product_name,
        "planned_changes": operations,
        "unsupported_fields": unsupported_fields,
        "errors": [],
        "write_allowlist": sorted(payloads),
        "protected_paths": [".git/**", ".usc/**", "licence/notice/attribution files", "all paths outside the adapter allowlist"],
        "read_only": True,
        "files_changed": False,
        "code_executed": False,
        "note": "Plan is deterministic and read-only. Apply revalidates inputs, paths, markers, and target contents before writing.",
    }
    return report, payloads


def create_nextjs_branding_plan(
    project_root: str | Path, project_config: str | Path, branding_config: str | Path,
) -> dict[str, Any]:
    """Create a read-only plan for the narrowly supported USC-marked Next.js layout."""
    try:
        report, _ = _build_plan(project_root, project_config, branding_config)
        return report
    except (OSError, UnicodeError, ValueError, KeyError, InspectionError) as exc:
        return {
            "schema_version": "1.0", "operation": "customization_dry_run",
            "adapter_id": "web-nextjs", "status": "blocked_unsafe_or_unsupported",
            "planned_changes": [], "unsupported_fields": [], "errors": [str(exc)],
            "read_only": True, "files_changed": False, "code_executed": False,
        }


def apply_nextjs_branding(
    project_root: str | Path,
    project_config: str | Path,
    branding_config: str | Path,
    *,
    approved: bool = False,
    expected_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply only the exact read-only plan that the caller reviewed and approved."""
    if not approved:
        return {
            "schema_version": "1.0", "operation": "customization_apply",
            "adapter_id": "web-nextjs", "status": "blocked_approval_required",
            "files_changed": False, "errors": ["Explicit --approve is required."],
        }
    if not isinstance(expected_plan, dict):
        return {
            "schema_version": "1.0", "operation": "customization_apply",
            "adapter_id": "web-nextjs", "status": "blocked_plan_review_required",
            "files_changed": False, "errors": ["A reviewed customize-plan report is required."],
        }
    try:
        project = _load_json(project_config)
        review = project.get("licence_review", {})
        if not isinstance(review, dict) or review.get("status") != "approved" or not isinstance(review.get("review_record"), dict):
            raise ValueError("Human licence review must be marked approved with a review_record before application.")
        report, payloads = _build_plan(project_root, project_config, branding_config)
        if expected_plan != report:
            raise ValueError("Reviewed plan no longer matches current project/configuration state; generate and review a fresh plan.")
        if report["status"] not in {"ready_for_review", "no_changes_needed"}:
            return {**report, "operation": "customization_apply", "status": "blocked_plan", "files_changed": False}
        root = Path(project_root).expanduser().resolve(strict=True)
        staged: dict[str, Path] = {}
        changed = []
        committed: list[tuple[str, Path, bytes | None, bytes, int]] = []
        modes: dict[str, int] = {}
        try:
            # Preflight every target and stage every payload before the first project write.
            for relative in sorted(payloads):
                target, updated, original = payloads[relative]
                current_target, current = _safe_target(root, relative)
                if current != original:
                    if original is None and current == updated:
                        continue
                    raise ValueError(f"Target changed after planning; refusing to write: {relative}")
                mode = stat.S_IMODE(current_target.stat().st_mode) if original is not None else 0o644
                modes[relative] = mode
                descriptor, temporary = tempfile.mkstemp(prefix=".usc-brand-stage-", dir=current_target.parent)
                try:
                    with os.fdopen(descriptor, "wb") as handle:
                        handle.write(updated)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.chmod(temporary, mode)
                except Exception:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
                    raise
                staged[relative] = Path(temporary)

            for relative in sorted(staged):
                target, updated, original = payloads[relative]
                current_target, current = _safe_target(root, relative)
                if current != original:
                    if original is None and current == updated:
                        continue
                    raise ValueError(f"Target changed during application; refusing to write: {relative}")
                if original is None:
                    # Hard-link creation is atomic and fails rather than replacing an existing path.
                    os.link(staged[relative], current_target)
                    committed.append((relative, current_target, original, updated, modes[relative]))
                    changed.append({"path": relative, "sha256": _digest(updated)})
                    os.unlink(staged[relative])
                    staged.pop(relative, None)
                else:
                    os.replace(staged[relative], current_target)
                    committed.append((relative, current_target, original, updated, modes[relative]))
                    changed.append({"path": relative, "sha256": _digest(updated)})
                    staged.pop(relative, None)
        except Exception as exc:
            rollback_errors = []
            for relative, target, original, updated, mode in reversed(committed):
                try:
                    safe_target, current = _safe_target(root, relative)
                    if current != updated:
                        raise ValueError(f"Refusing rollback because the file changed after write: {relative}")
                    if original is None:
                        safe_target.unlink()
                    else:
                        descriptor, temporary = tempfile.mkstemp(prefix=".usc-brand-rollback-", dir=safe_target.parent)
                        try:
                            with os.fdopen(descriptor, "wb") as handle:
                                handle.write(original)
                                handle.flush()
                                os.fsync(handle.fileno())
                            os.chmod(temporary, mode)
                            os.replace(temporary, safe_target)
                        finally:
                            if os.path.exists(temporary):
                                os.unlink(temporary)
                except Exception as rollback_exc:
                    rollback_errors.append(f"{relative}: {rollback_exc}")
            if rollback_errors:
                raise ValueError(
                    f"Application failed ({exc}); rollback was incomplete: " + "; ".join(rollback_errors)
                ) from exc
            raise
        finally:
            for temporary in staged.values():
                if temporary.exists():
                    temporary.unlink()
        return {
            "schema_version": "1.0", "operation": "customization_apply",
            "adapter_id": "web-nextjs", "status": "applied",
            "project_id": report.get("project_id"), "changed_files": changed,
            "change_report": [
                {**item, "status": "applied"}
                for item in report.get("planned_changes", [])
            ],
            "files_changed": bool(changed), "code_executed": False,
            "note": "Only explicitly allowlisted USC-marked files and USC-owned public asset names were written. No project scripts were executed.",
        }
    except (OSError, UnicodeError, ValueError, KeyError, InspectionError) as exc:
        return {
            "schema_version": "1.0", "operation": "customization_apply",
            "adapter_id": "web-nextjs", "status": "blocked_unsafe_or_unsupported",
            "files_changed": False, "errors": [str(exc)],
        }
