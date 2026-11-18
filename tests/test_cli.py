from customizer.cli import main


def test_cli_reports_foundation_stage(capsys):
    assert main() == 0
    output = capsys.readouterr().out
    assert "foundation stage" in output
    assert "no source-modification commands" in output
