"""Read-only adapter detection and deterministic customization planning."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .configuration import validate_project_branding_configuration
from .inspector import InspectionError, inspect_repository


# Detection labels are evidence-based suggestions, not executable adapters.
_FAMILY_ADAPTERS = {
    "nextjs": "web-nextjs",
    "react": "web-react",
    "vue": "web-vue",
    "angular": "web-angular",
    "vite": "web-vite",
    "nodejs": "web-node",
    "python": "python",
    "rust": "rust",
    "go": "go",
    "jvm": "jvm",
    "php": "php",
    "ruby": "ruby",
    "elixir": "elixir",
}


def detect_adapters(repository: str | Path) -> dict[str, Any]:
    """Return deterministic technology/adapter candidates without loading project code."""
    inspection = inspect_repository(repository)
    families = sorted(set(inspection["technology"]["families"]))
    candidates = [
        {
            "adapter_id": _FAMILY_ADAPTERS[family],
            "technology_family": family,
            "status": "implemented" if family == "nextjs" else "detected_not_implemented",
        }
        for family in families
        if family in _FAMILY_ADAPTERS
    ]
    return {
        "schema_version": "1.0",
        "operation": "adapter_detection",
        "status": "candidates_detected" if candidates else "no_supported_candidate",
        "technology_families": families,
        "candidates": candidates,
        "read_only": True,
        "code_executed": False,
        "note": "Detection is heuristic metadata analysis. An implemented label means a guarded adapter exists; it does not mean the project passed its adapter-specific checks or rights review.",
    }


def create_customization_dry_run(
    repository: str | Path,
    project_config: str | Path,
    branding_config: str | Path,
) -> dict[str, Any]:
    """Validate configuration and emit a stable plan without writing or executing anything."""
    validation = validate_project_branding_configuration(
        repository, project_config, branding_config,
    )
    detection = detect_adapters(repository)
    errors = sorted(validation["errors"])
    requested_adapter = validation.get("adapter")
    candidate_ids = [item["adapter_id"] for item in detection["candidates"]]

    if validation["status"] == "valid" and requested_adapter == "web-nextjs" and "web-nextjs" in candidate_ids:
        from .web_nextjs import create_nextjs_branding_plan
        return create_nextjs_branding_plan(repository, project_config, branding_config)

    if validation["status"] != "valid":
        status = "blocked_invalid_configuration"
    elif not candidate_ids:
        status = "blocked_no_adapter_candidate"
        errors.append("No adapter candidate was detected for this project.")
    elif requested_adapter not in candidate_ids and requested_adapter != "web":
        status = "blocked_adapter_mismatch"
        errors.append(
            f"Configured adapter {requested_adapter!r} does not match detected candidates: "
            + ", ".join(candidate_ids)
        )
    else:
        status = "adapter_not_implemented"
        errors.append(
            "A matching adapter implementation is not registered. No file changes can be planned or applied."
        )

    requested_fields = sorted(
        [
            *(f"brand.{key}" for key in validation.get("brand_fields", [])),
            *(f"visual.{key}" for key in validation.get("visual_fields", [])),
        ]
    )
    return {
        "schema_version": "1.0",
        "operation": "customization_dry_run",
        "status": status,
        "project_id": validation.get("project_id"),
        "configured_adapter": requested_adapter,
        "detected_candidates": candidate_ids,
        "requested_product_name": validation.get("product_name"),
        "requested_fields": requested_fields,
        "planned_changes": [],
        "unsupported_fields": requested_fields,
        "errors": sorted(set(errors)),
        "read_only": True,
        "code_executed": False,
        "files_changed": False,
        "note": "This is a planning interface only. No source, licence, attribution, Git, or USC metadata files were changed.",
    }
