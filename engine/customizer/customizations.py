"""Read-only validation for the declarative product-customization registry."""
from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse


REGISTRY_RELATIVE_PATH = ".usc/customizations.json"
_CATEGORIES = {
    "branding",
    "feature_workflow",
    "business_rule",
    "configuration",
    "data_api_contract",
    "integration",
    "engineering_asset",
}
_PROTECTION_MODES = {"preserve", "require_regression_tests", "block_for_review"}
_OWNERSHIP = {"custom_only", "mixed"}
_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_TEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_GLOB_CHARS = set("*?[]")


def _error(errors: list[str], message: str) -> None:
    if message not in errors:
        errors.append(message)


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _safe_relative_file(root: Path, value: Any, *, label: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value or value.strip() != value:
        _error(errors, f"{label} must be a non-empty, trimmed relative path.")
        return None
    raw_parts = value.split("/")
    if "\\" in value or "\x00" in value or any(char in value for char in _GLOB_CHARS):
        _error(errors, f"{label} must use exact POSIX paths; globs, backslashes, and NUL bytes are not supported: {value!r}.")
        return None
    if any(part in {"", ".", ".."} for part in raw_parts):
        _error(errors, f"{label} is not a normalized repository-relative path: {value!r}.")
        return None
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        _error(errors, f"{label} is not a safe repository-relative path: {value!r}.")
        return None
    if pure.parts[0] in {".git", ".usc"}:
        _error(errors, f"{label} may not reference reserved metadata paths: {value!r}.")
        return None

    current = root
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            _error(errors, f"{label} traverses a symlink and is not supported: {value!r}.")
            return None
    if not current.exists():
        _error(errors, f"{label} references a missing or stale file: {value!r}.")
        return None
    if not current.is_file():
        _error(errors, f"{label} must reference a file, not a directory: {value!r}.")
        return None
    return pure.as_posix()


def _unknown_keys(value: dict[str, Any], allowed: set[str], *, label: str, errors: list[str]) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        _error(errors, f"{label} contains unsupported field(s): {', '.join(unknown)}.")


def _validate_https_refs(value: Any, *, label: str, errors: list[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        _error(errors, f"{label} must be an array of HTTPS URLs.")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip() or item.strip() != item:
            _error(errors, f"{label}[{index}] must be a non-empty, trimmed HTTPS URL.")
            continue
        parsed = urlparse(item)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            _error(errors, f"{label}[{index}] must be a credential-free HTTPS URL without query or fragment.")
            continue
        if item in result:
            _error(errors, f"{label} contains a duplicate reference: {item!r}.")
            continue
        result.append(item)
    return result


def inspect_customization_registry(repository: str | Path) -> dict[str, Any]:
    """Validate .usc/customizations.json without changing or executing project files."""
    root_arg = Path(repository).expanduser()
    try:
        root = root_arg.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        return {
            "schema_version": "1.0",
            "operation": "customization_registry_check",
            "status": "blocked",
            "registry_path": REGISTRY_RELATIVE_PATH,
            "customization_count": 0,
            "entries": [],
            "errors": [f"Repository path cannot be resolved: {exc}"],
            "warnings": [],
            "feature_protection_enforced": False,
            "note": "Validation is read-only; no source files or synchronization state were changed.",
        }
    if not root.is_dir():
        return {
            "schema_version": "1.0",
            "operation": "customization_registry_check",
            "status": "blocked",
            "registry_path": REGISTRY_RELATIVE_PATH,
            "customization_count": 0,
            "entries": [],
            "errors": ["Repository path must be an existing directory."],
            "warnings": [],
            "feature_protection_enforced": False,
            "note": "Validation is read-only; no source files or synchronization state were changed.",
        }

    usc_dir = root / ".usc"
    registry_file = root / REGISTRY_RELATIVE_PATH
    if usc_dir.is_symlink():
        errors = [".usc metadata directory must not be a symlink."]
        return _report("blocked", errors, [], 0)
    if not usc_dir.exists():
        return _report("not_configured", [], [], 0)
    if not usc_dir.is_dir():
        return _report("blocked", [".usc exists but is not a directory."], [], 0)
    if registry_file.is_symlink():
        return _report("blocked", ["Customization registry file must not be a symlink."], [], 0)
    if not registry_file.exists():
        return _report("not_configured", [], [], 0)
    if not registry_file.is_file():
        return _report("blocked", ["Customization registry path is not a regular file."], [], 0)

    try:
        data = json.loads(
            registry_file.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return _report("blocked", [f"Customization registry is unreadable or invalid JSON: {exc}"], [], 0)

    errors: list[str] = []
    warnings: list[str] = []
    summaries: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return _report("blocked", ["Registry root must be a JSON object."], [], 0)
    _unknown_keys(data, {"schema_version", "project_id", "customizations"}, label="Registry", errors=errors)
    if data.get("schema_version") != "1.0":
        _error(errors, "schema_version must be the string '1.0'.")
    project_id = data.get("project_id")
    if project_id is not None and (not isinstance(project_id, str) or not project_id.strip()):
        _error(errors, "project_id must be a non-empty string when supplied.")
    entries = data.get("customizations")
    if not isinstance(entries, list) or not entries:
        _error(errors, "customizations must be a non-empty array.")
        entries = []

    seen_ids: set[str] = set()
    ownership_by_path: dict[str, str] = {}
    for index, entry in enumerate(entries):
        label = f"customizations[{index}]"
        if not isinstance(entry, dict):
            _error(errors, f"{label} must be a JSON object.")
            continue
        _unknown_keys(
            entry,
            {"id", "name", "purpose", "category", "protection_mode", "paths", "test_ids", "evidence_refs", "review_note"},
            label=label,
            errors=errors,
        )
        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not _ID_RE.fullmatch(entry_id):
            _error(errors, f"{label}.id must be a stable lowercase kebab-case identifier.")
            entry_id = None
        elif entry_id in seen_ids:
            _error(errors, f"Duplicate customization id: {entry_id}.")
        else:
            seen_ids.add(entry_id)

        for field in ("name", "purpose"):
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip() or value.strip() != value:
                _error(errors, f"{label}.{field} must be a non-empty, trimmed string.")

        category = entry.get("category")
        if not isinstance(category, str) or category not in _CATEGORIES:
            _error(errors, f"{label}.category must be one of: {', '.join(sorted(_CATEGORIES))}.")
        mode = entry.get("protection_mode")
        if not isinstance(mode, str) or mode not in _PROTECTION_MODES:
            _error(errors, f"{label}.protection_mode must be one of: {', '.join(sorted(_PROTECTION_MODES))}.")

        paths = entry.get("paths")
        normalized_paths: list[dict[str, str]] = []
        if not isinstance(paths, list) or not paths:
            _error(errors, f"{label}.paths must be a non-empty array of exact file paths.")
            paths = []
        seen_entry_paths: set[str] = set()
        has_mixed_path = False
        for path_index, path_item in enumerate(paths):
            path_label = f"{label}.paths[{path_index}]"
            if not isinstance(path_item, dict):
                _error(errors, f"{path_label} must be a JSON object.")
                continue
            _unknown_keys(path_item, {"path", "ownership"}, label=path_label, errors=errors)
            normalized = _safe_relative_file(root, path_item.get("path"), label=f"{path_label}.path", errors=errors)
            ownership = path_item.get("ownership")
            if not isinstance(ownership, str) or ownership not in _OWNERSHIP:
                _error(errors, f"{path_label}.ownership must be 'custom_only' or 'mixed'.")
                continue
            if normalized is None:
                continue
            if normalized in seen_entry_paths:
                _error(errors, f"{label} contains a duplicate path: {normalized}.")
                continue
            seen_entry_paths.add(normalized)
            has_mixed_path = has_mixed_path or ownership == "mixed"
            prior_ownership = ownership_by_path.get(normalized)
            if prior_ownership is not None and prior_ownership != ownership:
                _error(errors, f"Path {normalized!r} has inconsistent ownership declarations across registry entries.")
            ownership_by_path[normalized] = ownership
            normalized_paths.append({"path": normalized, "ownership": ownership})

        test_ids = entry.get("test_ids", [])
        if not isinstance(test_ids, list):
            _error(errors, f"{label}.test_ids must be an array of stable test identifiers.")
            test_ids = []
        clean_test_ids: list[str] = []
        for test_index, test_id in enumerate(test_ids):
            if not isinstance(test_id, str) or not _TEST_ID_RE.fullmatch(test_id):
                _error(errors, f"{label}.test_ids[{test_index}] is not a valid test identifier.")
            elif test_id in clean_test_ids:
                _error(errors, f"{label}.test_ids contains duplicate identifier {test_id!r}.")
            else:
                clean_test_ids.append(test_id)

        evidence_refs = _validate_https_refs(entry.get("evidence_refs"), label=f"{label}.evidence_refs", errors=errors)
        review_note = entry.get("review_note")
        if review_note is not None and (not isinstance(review_note, str) or not review_note.strip()):
            _error(errors, f"{label}.review_note must be a non-empty string when supplied.")
        if mode == "preserve" and has_mixed_path:
            _error(errors, f"{label} uses preserve mode for a mixed-ownership file; use regression tests or block for review.")
        if mode == "require_regression_tests" and not clean_test_ids:
            _error(errors, f"{label} requires at least one test_id for require_regression_tests mode.")
        if mode == "block_for_review" and not isinstance(review_note, str):
            _error(errors, f"{label} requires a review_note when protection_mode is block_for_review.")
        if mode == "preserve" and not clean_test_ids:
            warnings.append(f"{entry_id or label} has no test_ids; preservation declaration is not behavioural proof.")

        summaries.append({
            "id": entry_id,
            "name": entry.get("name") if isinstance(entry.get("name"), str) else None,
            "category": category if isinstance(category, str) else None,
            "protection_mode": mode if isinstance(mode, str) else None,
            "paths": normalized_paths,
            "test_ids": clean_test_ids,
            "evidence_ref_count": len(evidence_refs),
        })

    status = "blocked" if errors else "valid"
    return {
        "schema_version": "1.0",
        "operation": "customization_registry_check",
        "status": status,
        "registry_path": REGISTRY_RELATIVE_PATH,
        "customization_count": len(entries),
        "entries": summaries,
        "errors": errors,
        "warnings": warnings,
        "feature_protection_enforced": False,
        "note": (
            "Registry declarations are structurally valid. This command does not classify upstream changes, execute tests, enforce acceptance gates, or prove semantic preservation."
            if status == "valid" else
            "Registry validation failed. Correct the reported issues before relying on these declarations."
        ),
    }


def _report(status: str, errors: list[str], warnings: list[str], count: int) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "operation": "customization_registry_check",
        "status": status,
        "registry_path": REGISTRY_RELATIVE_PATH,
        "customization_count": count,
        "entries": [],
        "errors": errors,
        "warnings": warnings,
        "feature_protection_enforced": False,
        "note": (
            "No customization registry is configured; existing synchronization behaviour is unchanged."
            if status == "not_configured" else
            "Registry validation failed. Correct the reported issues before relying on these declarations."
        ),
    }
