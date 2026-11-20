from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
CONFIGURATION = ROOT / "configuration"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validator_for(schema_name: str) -> Draft202012Validator:
    schema = load_json(CONFIGURATION / schema_name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def errors(validator: Draft202012Validator, instance: dict) -> list[str]:
    return [error.message for error in validator.iter_errors(instance)]


def project_example() -> dict:
    return load_json(CONFIGURATION / "project.example.json")


def branding_example() -> dict:
    return load_json(CONFIGURATION / "branding.example.json")


def test_project_and_branding_schemas_are_valid_draft_2020_12_documents():
    validator_for("project.schema.json")
    validator_for("branding.schema.json")


def test_published_examples_validate_against_their_schemas():
    assert errors(validator_for("project.schema.json"), project_example()) == []
    assert errors(validator_for("branding.schema.json"), branding_example()) == []


@pytest.mark.parametrize("project_id", ["", "UpperCase", "has spaces", "../escape", "bad_name"])
def test_project_schema_rejects_invalid_project_ids(project_id: str):
    data = project_example()
    data["project_id"] = project_id
    assert errors(validator_for("project.schema.json"), data)


@pytest.mark.parametrize("url", [
    "http://github.com/example/repo",
    "https://user:password@example.com/repo",
    "https://example.com/repo?token=secret",
    "not-a-url",
])
def test_project_schema_rejects_unsafe_or_non_https_source_urls(url: str):
    data = project_example()
    data["source"]["repository_url"] = url
    assert errors(validator_for("project.schema.json"), data)


def test_project_schema_requires_a_review_record_when_licence_is_approved():
    data = project_example()
    data["licence_review"] = {"status": "approved", "review_record": None}
    assert errors(validator_for("project.schema.json"), data)


def test_project_schema_rejects_unknown_fields():
    data = project_example()
    data["execute_hook"] = "install.sh"
    assert errors(validator_for("project.schema.json"), data)


@pytest.mark.parametrize("color", ["red", "#123", "#GG0000", " #123456", "#12345678"])
def test_branding_schema_rejects_invalid_hex_colors(color: str):
    data = branding_example()
    data["visual"]["primary_color"] = color
    assert errors(validator_for("branding.schema.json"), data)


@pytest.mark.parametrize("url", [
    "http://example.com",
    "javascript:alert(1)",
    "https://user:password@example.com",
    "https://example.com/path?token=secret",
])
def test_branding_schema_rejects_non_https_or_credential_bearing_urls(url: str):
    data = branding_example()
    data["brand"]["website_url"] = url
    assert errors(validator_for("branding.schema.json"), data)


@pytest.mark.parametrize("asset_path", [
    "/etc/passwd",
    "../outside.svg",
    "branding/../../outside.svg",
    ".git/config",
    ".usc/customizations.json",
    "branding\\logo.svg",
    "branding/*.svg",
    "branding//logo.svg",
])
def test_branding_schema_rejects_unsafe_asset_paths(asset_path: str):
    data = branding_example()
    data["visual"]["logo_path"] = asset_path
    assert errors(validator_for("branding.schema.json"), data)


def test_branding_schema_rejects_unknown_fields():
    data = branding_example()
    data["apply_shell_command"] = "npm install"
    assert errors(validator_for("branding.schema.json"), data)


def test_branding_schema_rejects_blank_product_name():
    data = branding_example()
    data["brand"]["product_name"] = "   "
    assert errors(validator_for("branding.schema.json"), data)
