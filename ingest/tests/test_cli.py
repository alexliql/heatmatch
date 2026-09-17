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


def test_an_unknown_region_is_rejected() -> None:
    result = CliRunner().invoke(app, ["run", "--region", "atlantis"])
    assert result.exit_code != 0
    assert "unknown region" in result.output


def test_a_partial_region_run_refuses_to_rewrite_the_bundle() -> None:
    """The bundle is one flat set of files, so a partial write loses regions.

    Guarding at the CLI is the only place this can be caught: by the time
    `emit` sees the rows it has no way to know which regions were asked for.
    """
    result = CliRunner().invoke(app, ["run", "--region", "nova"])
    assert result.exit_code != 0
    assert "dropping every other region" in result.output
    # The escape hatch is offered, not hidden.
    assert "--no-write" in result.output


def test_no_write_is_available_for_partial_runs() -> None:
    write = {p.name: p for p in typer.main.get_command(app).commands["run"].params}["write"]
    assert "--no-write" in write.secondary_opts
    assert write.default is True
