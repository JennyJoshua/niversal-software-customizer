"""Read-only validation of USC project and branding configuration."""
from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


MAX_CONFIG_BYTES = 1_000_000
SCHEMA_FILES = {
    "project": "project.schema.json",
    "branding": "branding.schema.json",
}
_PROTECTED_NAMES = (
    "license", "licence", "copying", "notice", "authors", "copyright",
    "attribution", "third-party-notices", "third_party_notices",
)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> Any:
    if path.is_symlink():
        raise ValueError(f"Configuration file must not be a symlink: {path}")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"Configuration path must be a regular file: {path}")
    if resolved.stat().st_size > MAX_CONFIG_BYTES:
        raise ValueError(f"Configuration file exceeds the {MAX_CONFIG_BYTES}-byte safety limit: {path}")
    return json.loads(
        resolved.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
    )


def _schema_validator(kind: str) -> Draft202012Validator:
    schema_path = files("customizer").joinpath("schemas", SCHEMA_FILES[kind])
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _schema_errors(kind: str, data: Any) -> list[str]:
    validator = _schema_validator(kind)
    problems = sorted(
        validator.iter_errors(data),
        key=lambda error: (tuple(str(part) for part in error.absolute_path), error.message),
    )
    rendered = []
    for error in problems:
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        rendered.append(f"{kind} config {location}: {error.message}")
    return rendered


def _asset_is_protected(relative: PurePosixPath) -> bool:
    if not relative.parts or relative.parts[0].lower() in {".git", ".usc"}:
        return True
    for part in relative.parts:
        lowered = part.lower()
        if any(lowered.startswith(prefix) for prefix in _PROTECTED_NAMES):
            return True
    return False


def _validate_asset(root: Path, value: Any, label: str) -> tuple[str | None, str | None]:
    if not isinstance(value, str) or not value or value.strip() != value:
        return None, f"{label} must be a non-empty, trimmed repository-relative path."
    if "\\" in value or "\x00" in value:
        return None, f"{label} must use normalized POSIX path separators."
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None, f"{label} contains an unsafe or non-normalized path segment."
    relative = PurePosixPath(value)
    if relative.is_absolute() or not relative.parts:
        return None, f"{label} must be a relative path."
    if _asset_is_protected(relative):
        return None, f"{label} targets protected Git/USC metadata or a licence/notice/attribution path."
    current = root
    try:
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                return None, f"{label} traverses a symlink."
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None, f"{label} does not resolve to an existing file inside the selected project."
    if not resolved.is_file():
        return None, f"{label} must reference an existing regular file."
    return relative.as_posix(), None


def validate_project_branding_configuration(
    project_root: str | Path,
    project_config: str | Path,
    branding_config: str | Path,
) -> dict[str, Any]:
    """Validate config shape and repository-contained assets without writing or executing code."""
    root_arg = Path(project_root).expanduser()
    if root_arg.is_symlink():
        return _blocked("Project root must not be a symlink.")
    try:
        root = root_arg.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        return _blocked(f"Project root cannot be resolved: {exc}")
    if not root.is_dir():
        return _blocked("Project root must be an existing directory.")

    errors: list[str] = []
    configs: dict[str, Any] = {}
    for kind, supplied in (("project", project_config), ("branding", branding_config)):
        try:
            configs[kind] = _load_json(Path(supplied).expanduser())
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"{kind} config could not be read safely: {exc}")

    for kind, data in configs.items():
        errors.extend(_schema_errors(kind, data))

    assets: list[dict[str, str]] = []
    branding = configs.get("branding")
    if isinstance(branding, dict):
        visual = branding.get("visual")
        if isinstance(visual, dict):
            for field in ("logo_path", "favicon_path"):
                if field not in visual:
                    continue
                normalized, problem = _validate_asset(root, visual[field], f"branding.visual.{field}")
                if problem:
                    errors.append(problem)
                elif normalized is not None:
                    assets.append({"field": field, "path": normalized, "status": "valid"})

    errors = sorted(set(errors))
    project = configs.get("project")
    brand = configs.get("branding")
    return {
        "schema_version": "1.0",
        "operation": "project_branding_config_check",
        "status": "blocked" if errors else "valid",
        "project_id": project.get("project_id") if isinstance(project, dict) else None,
        "adapter": project.get("adapter") if isinstance(project, dict) else None,
        "product_name": (
            brand.get("brand", {}).get("product_name")
            if isinstance(brand, dict) and isinstance(brand.get("brand"), dict) else None
        ),
        "brand_fields": sorted(brand.get("brand", {}).keys()) if isinstance(brand, dict) and isinstance(brand.get("brand"), dict) else [],
        "visual_fields": sorted(brand.get("visual", {}).keys()) if isinstance(brand, dict) and isinstance(brand.get("visual"), dict) else [],
        "assets": sorted(assets, key=lambda item: (item["field"], item["path"])),
        "errors": errors,
        "warnings": [],
        "read_only": True,
        "code_executed": False,
        "note": (
            "Configuration is structurally valid and all declared assets resolve safely. This does not approve licensing, "
            "trademarks, or an adapter's ability to apply the requested fields."
            if not errors else
            "Configuration validation failed. No project files were changed or executed."
        ),
    }


def _blocked(message: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "operation": "project_branding_config_check",
        "status": "blocked",
        "project_id": None,
        "adapter": None,
        "product_name": None,
        "assets": [],
        "errors": [message],
        "warnings": [],
        "read_only": True,
        "code_executed": False,
        "note": "Configuration validation failed. No project files were changed or executed.",
    }
