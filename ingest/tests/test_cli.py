"""The CLI contract: `run` exists and accepts --region. Real pipeline tests
(dedupe rules, LL84 fuel math) land with their modules in T2/T8."""

from typer.testing import CliRunner

from ingest.cli import app


def test_run_command_is_registered() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "--region" in result.stdout
