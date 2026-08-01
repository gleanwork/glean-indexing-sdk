"""Tests for the `glean-idx` root group."""

from click.testing import CliRunner

from glean.indexing.cli.main import COMMANDS, cli


def test_every_registered_command_is_listed():
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    for name in COMMANDS:
        assert name in result.output


def test_every_registered_command_can_be_imported():
    """The registry holds import strings, so a typo would only surface on use."""
    runner = CliRunner()
    for name in COMMANDS:
        result = runner.invoke(cli, [name, "--help"])
        assert result.exit_code == 0, f"{name}: {result.output}"


def test_the_example_commands_survive_help_rewrapping():
    """Click rewraps help text, which would break these mid-token.

    The epilog exists to be copy-pasted, so the guidance is worthless if the
    commands arrive split across lines.
    """
    result = CliRunner().invoke(cli, ["--help"])

    assert "uvx --from glean-indexing-sdk glean-idx doctor" in result.output
    assert "uv run glean-idx run" in result.output


def test_short_help_flag_works():
    assert CliRunner().invoke(cli, ["-h"]).exit_code == 0
