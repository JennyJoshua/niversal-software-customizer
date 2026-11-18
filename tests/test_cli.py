import json

from customizer import cli


def test_cli_inspects_local_directory(tmp_path, capsys):
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "demo", "dependencies": {"react": "18"}}),
        encoding="utf-8",
    )

    result = cli.main(["inspect", "--path", str(tmp_path)])

    assert result == 0
    report = json.loads(capsys.readouterr().out)
    assert report["result"] == "supported_candidate"
    assert report["source"] == str(tmp_path.resolve())
    assert report["safety"]["executed_source_code"] is False


def test_cli_returns_one_for_unsupported_project(tmp_path, capsys):
    (tmp_path / "readme.txt").write_text("not a known project", encoding="utf-8")

    result = cli.main(["inspect", "--path", str(tmp_path)])

    assert result == 1
    report = json.loads(capsys.readouterr().out)
    assert report["result"] == "unsupported"


def test_cli_reports_inspection_error(tmp_path, capsys):
    result = cli.main(["inspect", "--path", str(tmp_path / "missing")])

    captured = capsys.readouterr()
    assert result == 2
    assert captured.out == ""
    assert "Source path must be an existing directory" in captured.err


def test_cli_calls_pinned_github_inspector(monkeypatch, capsys):
    expected = {
        "result": "supported_candidate",
        "source": {"repository_url": "https://github.com/acme/demo.git", "requested_revision": "v1.0.0"},
        "commit": "a" * 40,
    }
    calls = []

    def fake_inspect(url, revision):
        calls.append((url, revision))
        return expected

    monkeypatch.setattr(cli, "inspect_github_repository", fake_inspect)

    result = cli.main([
        "inspect",
        "--repo-url", "https://github.com/acme/demo",
        "--revision", "v1.0.0",
    ])

    assert result == 0
    assert calls == [("https://github.com/acme/demo", "v1.0.0")]
    assert json.loads(capsys.readouterr().out) == expected


def test_cli_requires_revision_for_remote_repository():
    import pytest

    with pytest.raises(SystemExit) as exc:
        cli.main(["inspect", "--repo-url", "https://github.com/acme/demo"])
    assert exc.value.code == 2


def test_cli_rejects_revision_for_local_path():
    import pytest

    with pytest.raises(SystemExit) as exc:
        cli.main(["inspect", "--path", ".", "--revision", "main"])
    assert exc.value.code == 2
