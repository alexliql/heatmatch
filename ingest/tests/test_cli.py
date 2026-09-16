"""The CLI contract: `run` is a subcommand and accepts --region.

Asserts against the parsed command tree rather than rendered help text — Typer
renders help through Rich, which wraps to terminal width and injects ANSI
codes, so a substring check on stdout passes locally and fails on an 80-column
CI runner.
"""

import typer.main
from typer.testing import CliRunner

from ingest.cli import app


def test_run_is_a_subcommand_accepting_region() -> None:
    group = typer.main.get_command(app)
    # A regression guard: without the callback in cli.py, Typer would collapse
    # the single command into the root and `ingest run` would not exist.
    assert hasattr(group, "commands"), "app must stay a group so `ingest run` works"

    region = {p.name: p for p in group.commands["run"].params}["region"]
    assert "--region" in region.opts
    assert region.default == "all"


def test_run_help_exits_cleanly() -> None:
    assert CliRunner().invoke(app, ["run", "--help"]).exit_code == 0
