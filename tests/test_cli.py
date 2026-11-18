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
