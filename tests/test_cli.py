import json

from customizer.cli import main


def test_cli_outputs_inspection_report(tmp_path, capsys):
    source = tmp_path / "source"
    source.mkdir()
    (source / "package.json").write_text('{"name":"sample","dependencies":{"react":"18"}}', encoding="utf-8")

    assert main(["inspect", "--path", str(source)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["result"] == "supported_candidate"
    assert "react" in report["technology"]["families"]


def test_cli_writes_report_outside_source(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "notes.txt").write_text("sample", encoding="utf-8")
    output = tmp_path / "inspection.json"

    assert main(["inspect", "--path", str(source), "--output", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["result"] == "unsupported"



def test_licences_cli_emits_blocked_json(tmp_path, capsys):
    from customizer.cli import main

    (tmp_path / "LICENSE").write_text("Project licence evidence", encoding="utf-8")
    assert main(["licences", "--path", str(tmp_path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["customization_gate"] == "blocked"
    assert report["legal_approval"] is False


def test_licences_cli_writes_report_outside_source(tmp_path):
    from customizer.cli import main

    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "rights-review.json"
    assert main(["licences", "--path", str(source), "--output", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["review_status"] == "human_review_required"


def test_licences_cli_rejects_report_inside_source(tmp_path, capsys):
    from customizer.cli import main

    output = tmp_path / "rights-review.json"
    assert main(["licences", "--path", str(tmp_path), "--output", str(output)]) == 2
    assert "outside the inspected source directory" in capsys.readouterr().err


def test_sync_plan_cli_emits_read_only_plan(tmp_path, capsys):
    import subprocess

    from customizer.cli import main

    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, text=True, capture_output=True
        ).stdout.strip()

    git("init", "-q")
    git("config", "user.email", "tests@example.invalid")
    git("config", "user.name", "USC tests")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    (repo / "upstream.txt").write_text("upstream\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "upstream")
    target = git("rev-parse", "HEAD")
    git("reset", "--hard", base)
    (repo / "custom.txt").write_text("custom\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "custom")
    customized = git("rev-parse", "HEAD")

    output = tmp_path / "plan.json"
    assert main([
        "sync-plan", "--path", str(repo),
        "--base-sha", base, "--target-sha", target,
        "--output", str(output),
    ]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "ready_for_review"
    assert report["integration_performed"] is False
    assert git("rev-parse", "HEAD") == customized
    assert not (repo / "upstream.txt").exists()


def test_sync_plan_cli_rejects_output_inside_repository(tmp_path, capsys):
    import subprocess

    from customizer.cli import main

    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, text=True, capture_output=True
        ).stdout.strip()

    git("init", "-q")
    git("config", "user.email", "tests@example.invalid")
    git("config", "user.name", "USC tests")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")

    assert main([
        "sync-plan", "--path", str(repo),
        "--base-sha", base, "--target-sha", base,
        "--output", str(repo / "plan.json"),
    ]) == 2
    assert "outside the inspected source directory" in capsys.readouterr().err


def test_sync_candidate_cli_requires_approval_and_writes_report(tmp_path, capsys):
    import subprocess

    from customizer.cli import main

    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, text=True, capture_output=True
        ).stdout.strip()

    git("init", "-q")
    git("config", "user.email", "tests@example.invalid")
    git("config", "user.name", "USC tests")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    (repo / "upstream.txt").write_text("upstream\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "upstream")
    target = git("rev-parse", "HEAD")
    git("branch", "upstream/test", target)
    git("reset", "--hard", base)
    (repo / "custom.txt").write_text("custom\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "custom")
    original_head = git("rev-parse", "HEAD")

    workspace = tmp_path / "candidate"
    assert main([
        "sync-candidate", "--path", str(repo),
        "--base-sha", base, "--target-sha", target,
        "--workspace", str(workspace),
    ]) == 2
    assert "explicit --approve" in capsys.readouterr().err
    assert not workspace.exists()

    output = tmp_path / "candidate-report.json"
    assert main([
        "sync-candidate", "--path", str(repo),
        "--base-sha", base, "--target-sha", target,
        "--workspace", str(workspace), "--approve",
        "--output", str(output),
    ]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "candidate_ready_for_review"
    assert report["integration_committed"] is False
    assert git("rev-parse", "HEAD") == original_head
