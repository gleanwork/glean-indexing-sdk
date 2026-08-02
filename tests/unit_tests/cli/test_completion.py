"""Tests for `glean-idx completion`."""

import pytest
from click.testing import CliRunner

from glean.indexing.cli.commands.completion import COMPLETE_VAR, SHELLS, completion


@pytest.mark.parametrize("shell", SHELLS)
def test_each_shell_gets_a_script(shell):
    result = CliRunner().invoke(completion, [shell])

    assert result.exit_code == 0, result.output
    assert len(result.stdout.strip().splitlines()) > 3


@pytest.mark.parametrize("shell", SHELLS)
def test_the_script_names_the_variable_the_installed_command_looks_for(shell):
    """A mismatched variable name yields a script that silently completes nothing."""
    result = CliRunner().invoke(completion, [shell])

    assert COMPLETE_VAR in result.stdout
    assert "glean-idx" in result.stdout


def test_the_install_hint_stays_off_stdout():
    """`glean-idx completion zsh >> ~/.zshrc` has to capture only the script."""
    result = CliRunner().invoke(completion, ["zsh"])

    assert "Add it with" in result.stderr
    assert "Add it with" not in result.stdout


def test_an_unsupported_shell_is_a_usage_error():
    result = CliRunner().invoke(completion, ["powershell"])

    assert result.exit_code != 0
    assert "powershell" in result.output
