"""Collect licence and third-party rights evidence for human review.

This module reports technical evidence only. It never grants legal clearance.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any

from .inspector import IGNORED_DIRS, MAX_FILES, MAX_MANIFEST_BYTES

MAX_EVIDENCE_BYTES = 2_000_000
MAX_DEPENDENCIES = 1000
ASSET_EXTENSIONS = {
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
    ".svg": "image_or_icon", ".webp": "image", ".ico": "image",
    ".woff": "font", ".woff2": "font", ".ttf": "font", ".otf": "font",
    ".eot": "font", ".mp3": "audio", ".mp4": "video", ".pdf": "document",
    ".csv": "dataset_or_tabular_data", ".jsonl": "dataset_or_tabular_data",
    ".parquet": "dataset_or_tabular_data",
}
ASSET_DIR_HINTS = {
    "assets": "asset", "public": "public_asset", "static": "static_asset",
    "fonts": "font", "font": "font", "icons": "icon", "images": "image",
    "data": "data_or_dataset", "datasets": "dataset", "logos": "logo_or_trademark",
}


class LicenceScanError(ValueError):
    """Raised when a source directory cannot be scanned safely."""


def _safe_files(root: Path) -> tuple[list[str], bool]:
    found: list[str] = []
    truncated = False
    for current, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            name for name in dirs
            if name not in (IGNORED_DIRS - {"vendor"}) and not (Path(current) / name).is_symlink()
        )
        for name in sorted(names):
            path = Path(current) / name
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                found.append(path.relative_to(root).as_posix())
            except (OSError, ValueError):
                continue
            if len(found) >= MAX_FILES:
                truncated = True
                return found, truncated
    return found, truncated


def _read_limited(path: Path, limit: int = MAX_EVIDENCE_BYTES) -> bytes | None:
    try:
        if path.stat().st_size > limit:
            return None
        return path.read_bytes()
    except OSError:
        return None


def _evidence_category(filename: str) -> str | None:
    lowered = filename.lower()
    if lowered.startswith(("license", "licence", "copying")):
        return "licence"
    if lowered.startswith("notice") or lowered.startswith("third-party-notices"):
        return "notice"
    if lowered.startswith("authors"):
        return "authors"
    if lowered.startswith("attribution"):
        return "attribution"
    if lowered.startswith("copyright"):
        return "copyright"
    return None


def _metadata(root: Path, relative: str) -> dict[str, Any] | None:
    path = root / relative
    raw = _read_limited(path, MAX_MANIFEST_BYTES)
    if raw is None:
        return None
    try:
        if path.name == "package.json" or path.name == "composer.json":
            value = json.loads(raw.decode("utf-8"))
        elif path.name in {"pyproject.toml", "Cargo.toml"}:
            value = tomllib.loads(raw.decode("utf-8"))
        else:
            return None
        return value if isinstance(value, dict) else None
    except (UnicodeError, json.JSONDecodeError, tomllib.TOMLDecodeError):
        return None


def _declared_project_licences(root: Path, manifests: list[str]) -> list[dict[str, str]]:
    declarations: list[dict[str, str]] = []
    for relative in manifests:
        data = _metadata(root, relative)
        if not data:
            continue
        value: Any = None
        if relative.endswith("package.json"):
            value = data.get("license")
        elif relative.endswith("composer.json"):
            value = data.get("license")
        elif relative.endswith("pyproject.toml"):
            project = data.get("project", {})
            value = project.get("license") if isinstance(project, dict) else None
        elif relative.endswith("Cargo.toml"):
            package = data.get("package", {})
            value = package.get("license") if isinstance(package, dict) else None
        if isinstance(value, str) and value.strip():
            declarations.append({"manifest": relative, "expression": value.strip()})
        elif isinstance(value, dict):
            # PEP 639 license tables and package metadata file references are recorded,
            # but their content is not interpreted as an SPDX expression.
            declarations.append({
                "manifest": relative,
                "expression": "metadata_file_reference_or_table",
            })
    return declarations


def _dependencies(root: Path, manifests: list[str]) -> list[dict[str, str]]:
    dependencies: list[dict[str, str]] = []
    for relative in manifests:
        path = root / relative
        raw = _read_limited(path, MAX_MANIFEST_BYTES)
        if raw is None:
            continue
        try:
            if path.name == "package.json":
                data = json.loads(raw.decode("utf-8"))
                for section in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
                    values = data.get(section, {}) if isinstance(data, dict) else {}
                    if isinstance(values, dict):
                        for name, version in values.items():
                            dependencies.append({
                                "ecosystem": "npm", "name": str(name),
                                "constraint": str(version), "manifest": relative,
                            })
            elif path.name == "composer.json":
                data = json.loads(raw.decode("utf-8"))
                for section in ("require", "require-dev") if isinstance(data, dict) else ():
                    values = data.get(section, {})
                    if isinstance(values, dict):
                        for name, version in values.items():
                            if name != "php":
                                dependencies.append({
                                    "ecosystem": "composer", "name": str(name),
                                    "constraint": str(version), "manifest": relative,
                                })
            elif path.name in {"pyproject.toml", "Cargo.toml"}:
                data = tomllib.loads(raw.decode("utf-8"))
                if path.name == "pyproject.toml":
                    project = data.get("project", {})
                    specs = project.get("dependencies", []) if isinstance(project, dict) else []
                    optional = project.get("optional-dependencies", {}) if isinstance(project, dict) else {}
                    for spec in specs if isinstance(specs, list) else []:
                        match = re.match(r"\s*([A-Za-z0-9_.-]+)\s*(.*)", str(spec))
                        if match:
                            dependencies.append({
                                "ecosystem": "pypi", "name": match.group(1),
                                "constraint": match.group(2).strip(), "manifest": relative,
                            })
                    if isinstance(optional, dict):
                        for group, specs in optional.items():
                            for spec in specs if isinstance(specs, list) else []:
                                match = re.match(r"\s*([A-Za-z0-9_.-]+)\s*(.*)", str(spec))
                                if match:
                                    dependencies.append({
                                        "ecosystem": "pypi", "name": match.group(1),
                                        "constraint": match.group(2).strip(),
                                        "manifest": relative, "group": str(group),
                                    })
                else:
                    package = data.get("dependencies", {})
                    if isinstance(package, dict):
                        for name, spec in package.items():
                            dependencies.append({
                                "ecosystem": "cargo", "name": str(name),
                                "constraint": str(spec), "manifest": relative,
                            })
            elif path.name == "requirements.txt":
                for line in raw.decode("utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if not line or line.startswith(("#", "-", "git+", "http:")):
                        continue
                    match = re.match(r"([A-Za-z0-9_.-]+)\s*(.*)", line)
                    if match:
                        dependencies.append({
                            "ecosystem": "pypi", "name": match.group(1),
                            "constraint": match.group(2).strip(), "manifest": relative,
                        })
            elif path.name == "go.mod":
                for line in raw.decode("utf-8", errors="replace").splitlines():
                    match = re.match(r"\s*([A-Za-z0-9._~/-]+)\s+(v[^\s]+)", line)
                    if match:
                        dependencies.append({
                            "ecosystem": "go", "name": match.group(1),
                            "constraint": match.group(2), "manifest": relative,
                        })
        except (UnicodeError, json.JSONDecodeError, tomllib.TOMLDecodeError, AttributeError):
            continue
        if len(dependencies) >= MAX_DEPENDENCIES:
            return dependencies[:MAX_DEPENDENCIES]
    return dependencies


def _asset_and_rights_hints(files: list[str]) -> dict[str, Any]:
    items: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    for relative in files:
        path = Path(relative)
        parts = {part.lower() for part in path.parts[:-1]}
        category = ASSET_EXTENSIONS.get(path.suffix.lower())
        if category is None:
            category = next((ASSET_DIR_HINTS[p] for p in parts if p in ASSET_DIR_HINTS), None)
        if category:
            counts[category] = counts.get(category, 0) + 1
            if len(items) < 200:
                items.append({"path": relative, "category": category})
    return {
        "detected_categories": sorted(counts),
        "counts": counts,
        "items": items,
        "truncated": sum(counts.values()) > len(items),
        "warning": (
            "Asset, font, icon, image, dataset, logo, and trademark rights are not "
            "established by the project licence and require separate review."
        ),
        "trademark_review_required": True,
    }


def scan_licence_evidence(source: str | Path) -> dict[str, Any]:
    """Create a static evidence report; every report remains unapproved."""
    root = Path(source).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise LicenceScanError("Source path must be an existing directory.")

    files, inventory_truncated = _safe_files(root)
    evidence_files: list[dict[str, Any]] = []
    for relative in files:
        category = _evidence_category(Path(relative).name)
        if not category:
            continue
        raw = _read_limited(root / relative)
        if raw is None:
            evidence_files.append({
                "path": relative, "category": category,
                "readable": False, "content_sha256": None,
                "spdx_identifiers": [],
            })
            continue
        text = raw.decode("utf-8", errors="replace")
        identifiers = sorted(set(re.findall(
            r"SPDX-License-Identifier:\s*([^\r\n*]+)", text, flags=re.IGNORECASE
        )))
        evidence_files.append({
            "path": relative, "category": category, "readable": True,
            "size_bytes": len(raw),
            "content_sha256": hashlib.sha256(raw).hexdigest(),
            "spdx_identifiers": [value.strip() for value in identifiers],
        })

    root_evidence = [item for item in evidence_files if "/" not in item["path"]]
    nested_evidence = [item for item in evidence_files if "/" in item["path"]]
    root_licences = [item for item in root_evidence if item["category"] == "licence"]
    nested_licences = [item for item in nested_evidence if item["category"] == "licence"]
    manifests = [
        item for item in files
        if Path(item).name in {
            "package.json", "composer.json", "pyproject.toml", "Cargo.toml",
            "requirements.txt", "go.mod",
        }
    ]
    root_manifests = [item for item in manifests if "/" not in item]
    declarations = _declared_project_licences(root, root_manifests)
    declared_values = sorted(set(item["expression"] for item in declarations))
    spdx_values = sorted(set(
        identifier for item in root_licences for identifier in item["spdx_identifiers"]
    ))
    conflicts: list[str] = []
    if len(declared_values) > 1:
        conflicts.append("Multiple project licence declarations disagree or require interpretation.")
    if len(spdx_values) > 1:
        conflicts.append("Multiple SPDX identifiers appear in root licence evidence.")
    if declared_values and spdx_values:
        normalized_declared = {value.casefold() for value in declared_values}
        normalized_spdx = {value.casefold() for value in spdx_values}
        if normalized_declared.isdisjoint(normalized_spdx):
            conflicts.append("Manifest licence declaration differs from SPDX identifier in root licence evidence.")

    missing_root_licence = not root_licences and not declarations
    if missing_root_licence:
        conflicts.append("No root project licence file or supported manifest licence declaration was found.")
    if any(not item["readable"] for item in evidence_files):
        conflicts.append("One or more rights-evidence files could not be read within the configured size limit.")
    if inventory_truncated:
        conflicts.append("File inventory reached its safety limit; evidence scan may be incomplete.")

    dependencies = _dependencies(root, manifests)
    return {
        "schema_version": 1,
        "source": str(root),
        "review_status": "human_review_required",
        "customization_gate": "blocked",
        "legal_approval": False,
        "project_licence": {
            "root_evidence_files": root_licences,
            "nested_evidence_files": nested_licences,
            "manifest_declarations": declarations,
            "spdx_identifiers_found": spdx_values,
            "missing_root_licence_evidence": missing_root_licence,
            "conflicts": conflicts,
            "interpretation": (
                "Evidence signals only. File presence, metadata declarations, and SPDX tags "
                "do not establish legal permission or licence compatibility."
            ),
        },
        "other_rights_evidence": {
            "root_notice_author_authorship_files": [
                item for item in root_evidence if item["category"] != "licence"
            ],
            "nested_notice_author_authorship_files": [
                item for item in nested_evidence if item["category"] != "licence"
            ],
            "assets_fonts_data_and_trademarks": _asset_and_rights_hints(files),
        },
        "dependencies": {
            "declared_count": len(dependencies),
            "items": dependencies,
            "licence_status": "not_resolved",
            "warning": "Dependency licences are not inferred from package names or version constraints.",
            "truncated": len(dependencies) >= MAX_DEPENDENCIES,
        },
        "review_record": {
            "intended_use": "not_recorded",
            "reviewer": None,
            "reviewed_at": None,
            "decision": "pending_human_review",
            "obligations": [],
            "unresolved_questions": [
                "Confirm the exact project licence and its terms.",
                "Review every dependency and its applicable licence/version.",
                "Review assets, fonts, icons, datasets, documentation, and other third-party materials.",
                "Check trademarks, logos, and brand permissions separately.",
                "Confirm obligations for the intended modification, deployment, and distribution model.",
            ],
        },
        "safety": {
            "read_only": True,
            "executed_source_code": False,
            "legal_conclusion_issued": False,
            "file_limit": MAX_FILES,
            "evidence_file_size_limit_bytes": MAX_EVIDENCE_BYTES,
        },
        "limitations": [
            "This report is not legal advice and cannot approve a project.",
            "Dependency licence resolution and asset-by-asset rights verification require human review.",
            "Nested licence files may apply only to their own subcomponents; scope must be checked.",
            "A missing, ambiguous, conflicting, or incomplete evidence set blocks customization.",
        ],
    }
