"""The CLI contract: `run` is a subcommand and accepts --region.

Asserts against the parsed command tree rather than rendered help text — Typer
renders help through Rich, which wraps to terminal width and injects ANSI
codes, so a substring check on stdout passes locally and fails on an 80-column
CI runner.
"""

import pytest
import typer
import typer.main
from typer.testing import CliRunner

from ingest.cli import _check_writable, _resolve, app
from ingest.config import REGIONS


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
    with pytest.raises(typer.BadParameter) as exc:
        _resolve("atlantis")
    assert "unknown region" in str(exc.value)
    # Every real region is named, so the message stays right as regions are added.
    for region in REGIONS:
        assert region in str(exc.value)


def test_a_partial_region_run_refuses_to_rewrite_the_bundle() -> None:
    """The bundle is one flat set of files, so a partial write loses regions.

    Guarding at the CLI is the only place this can be caught: by the time
    `emit` sees the rows it has no way to know which regions were asked for.
    """
    with pytest.raises(typer.BadParameter) as exc:
        _check_writable("nova", write=True)
    message = str(exc.value)
    assert "dropping every other region" in message
    # Both ways out are offered, not hidden.
    assert "--region all" in message and "--no-write" in message

    # The two cases that must be allowed through.
    _check_writable("all", write=True)
    _check_writable("nova", write=False)


def test_the_refusal_actually_reaches_the_command_line() -> None:
    """The guard is wired in, not just defined.

    Only the exit code is asserted: the message reaches the terminal through
    Rich, which wraps to the runner's width, so a substring check here passes
    locally and fails on an 80-column CI runner. The wording is checked above.
    """
    assert CliRunner().invoke(app, ["run", "--region", "nova"]).exit_code != 0


def test_no_write_is_available_for_partial_runs() -> None:
    write = {p.name: p for p in typer.main.get_command(app).commands["run"].params}["write"]
    assert "--no-write" in write.secondary_opts
    assert write.default is True
