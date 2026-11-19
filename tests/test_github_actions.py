from __future__ import annotations

import json
from urllib.parse import urlparse

import pytest

from customizer.github_actions import authenticate_github_actions_run
from customizer.sync import SyncPlanError


RUN_URL = "https://github.com/acme/fork/actions/runs/12345"
REPO = "acme/fork"
HEAD = "a" * 40
PARENT = "f" * 40
BRANCH = "usc-verify/candidate-123"
TREE = "b" * 40
WORKFLOW_BLOB = "c" * 40
WORKFLOW_PATH = ".github/workflows/ci.yml"


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


def make_payloads():
    run = {
        "id": 12345,
        "repository": {"full_name": REPO},
        "status": "completed",
        "conclusion": "success",
        "event": "push",
        "head_branch": BRANCH,
        "head_sha": HEAD,
        "workflow_id": 42,
        "path": WORKFLOW_PATH,
    }
    return {
        "/actions/runs/12345": run,
        f"/git/commits/{HEAD}": {"tree": {"sha": TREE}, "parents": [{"sha": PARENT}]},
        f"/contents/{WORKFLOW_PATH}?ref={HEAD}": {"sha": WORKFLOW_BLOB},
        "/actions/runs/12345/jobs?per_page=100": {
            "total_count": 1,
            "jobs": [{"status": "completed", "conclusion": "success"}],
        },
    }


def verify(monkeypatch, payloads):
    import customizer.github_actions as module

    def fake_urlopen(request, timeout):
        path = urlparse(request.full_url).path.removeprefix("/repos/acme/fork")
        query = urlparse(request.full_url).query
        key = path + (f"?{query}" if query else "")
        if key not in payloads:
            raise AssertionError(f"Unexpected GitHub API request: {key}")
        return FakeResponse(payloads[key])

    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    return authenticate_github_actions_run(
        RUN_URL,
        expected_repository=REPO,
        expected_tree_sha=TREE,
        expected_workflow_id=42,
        expected_workflow_path=WORKFLOW_PATH,
        expected_workflow_blob_sha=WORKFLOW_BLOB,
        expected_head_sha=HEAD,
        expected_parent_sha=PARENT,
        expected_branch=BRANCH,
    )


def test_authenticates_successful_run_for_exact_candidate_tree_and_pinned_workflow(monkeypatch):
    result = verify(monkeypatch, make_payloads())

    assert result["authenticated"] is True
    assert result["repository"] == REPO
    assert result["head_sha"] == HEAD
    assert result["parent_sha"] == PARENT
    assert result["candidate_tree_sha"] == TREE
    assert result["workflow_blob_sha"] == WORKFLOW_BLOB
    assert result["job_count"] == 1


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("repository", {"full_name": "someone/else"}, "different repository"),
        ("status", "in_progress", "completed"),
        ("conclusion", "failure", "conclusion=success"),
        ("event", "pull_request", "push-triggered"),
        ("head_branch", "main", "usc-verify/"),
        ("workflow_id", 99, "pinned workflow identity"),
        ("path", ".github/workflows/other.yml", "pinned workflow identity"),
    ],
)
def test_rejects_untrusted_run_metadata(monkeypatch, field, value, message):
    payloads = make_payloads()
    payloads["/actions/runs/12345"][field] = value

    with pytest.raises(SyncPlanError, match=message):
        verify(monkeypatch, payloads)


def test_rejects_run_whose_commit_tree_is_not_the_candidate(monkeypatch):
    payloads = make_payloads()
    payloads[f"/git/commits/{HEAD}"]["tree"]["sha"] = "d" * 40

    with pytest.raises(SyncPlanError, match="exact candidate tree"):
        verify(monkeypatch, payloads)


def test_rejects_changed_trusted_workflow_blob(monkeypatch):
    payloads = make_payloads()
    payloads[f"/contents/{WORKFLOW_PATH}?ref={HEAD}"]["sha"] = "e" * 40

    with pytest.raises(SyncPlanError, match="trusted workflow blob"):
        verify(monkeypatch, payloads)


def test_rejects_failed_or_incomplete_jobs(monkeypatch):
    payloads = make_payloads()
    payloads["/actions/runs/12345/jobs?per_page=100"]["jobs"][0]["conclusion"] = "failure"

    with pytest.raises(SyncPlanError, match="Every job"):
        verify(monkeypatch, payloads)


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/acme/fork/actions/runs/12345",
        "https://evil.example/acme/fork/actions/runs/12345",
        "https://github.com/acme/fork/actions/runs/12345?redirect=evil",
        "https://github.com/acme/fork/actions/runs/not-a-number",
        "https://user@github.com/acme/fork/actions/runs/12345",
    ],
)
def test_rejects_noncanonical_or_untrusted_run_urls(url):
    with pytest.raises(SyncPlanError, match="canonical https"):
        authenticate_github_actions_run(
            url,
            expected_repository=REPO,
            expected_tree_sha=TREE,
            expected_workflow_id=42,
            expected_workflow_path=WORKFLOW_PATH,
            expected_workflow_blob_sha=WORKFLOW_BLOB,
        )


def test_rejects_wrong_snapshot_commit_sha(monkeypatch):
    payloads = make_payloads()
    payloads["/actions/runs/12345"]["head_sha"] = "d" * 40
    with pytest.raises(SyncPlanError, match="snapshot commit SHA"):
        verify(monkeypatch, payloads)


def test_rejects_wrong_snapshot_parent(monkeypatch):
    payloads = make_payloads()
    payloads[f"/git/commits/{HEAD}"]["parents"] = [{"sha": "e" * 40}]
    with pytest.raises(SyncPlanError, match="sole parent"):
        verify(monkeypatch, payloads)


def test_rejects_wrong_snapshot_branch(monkeypatch):
    payloads = make_payloads()
    payloads["/actions/runs/12345"]["head_branch"] = "usc-verify/other"
    with pytest.raises(SyncPlanError, match="published verification snapshot"):
        verify(monkeypatch, payloads)
