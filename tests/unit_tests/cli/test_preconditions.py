"""The `@requires` decorator, exercised through throwaway commands.

Preconditions are checked before any work runs, so these assert both the failure
shape and that the command body never executed.
"""

import json

import click
import pytest
from click.testing import CliRunner

from glean.indexing.cli.errors import EXIT_OK, EXIT_PRECONDITION
from glean.indexing.cli.main import context, global_options
from glean.indexing.cli.output import set_output_mode
from glean.indexing.cli.preconditions import (
    missing_credentials,
    project_option,
    requires,
)
from glean.indexing.cli.project import PROJECT_FILE

ENV_VARS = ("GLEAN_SERVER_URL", "GLEAN_INSTANCE", "GLEAN_INDEXING_API_TOKEN")


@pytest.fixture()
def runner(monkeypatch):
    """A runner with the Glean environment cleared."""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    set_output_mode(None)
    return CliRunner()


@pytest.fixture()
def ran():
    """Records whether a command body executed."""
    return []


def _build(ran, **needs):
    @click.command()
    @project_option
    @global_options
    @click.pass_context
    @requires(**needs)
    def command(ctx, project_dir, output, assume_yes):
        context(ctx, output=output, assume_yes=assume_yes, project_dir=project_dir)
        ran.append(True)

    return command


def test_credentials_requirement_blocks_the_body(runner, ran):
    result = runner.invoke(_build(ran, credentials=True), ["--output", "json"])
    assert result.exit_code == EXIT_PRECONDITION
    assert json.loads(result.output)["error"]["code"] == "missing_credentials"
    assert ran == []


def test_credentials_requirement_passes_when_set(runner, ran, monkeypatch):
    monkeypatch.setenv("GLEAN_SERVER_URL", "https://acme-be.glean.com")
    monkeypatch.setenv("GLEAN_INDEXING_API_TOKEN", "t")
    result = runner.invoke(_build(ran, credentials=True), ["--output", "json"])
    assert result.exit_code == EXIT_OK
    assert ran == [True]


def test_legacy_instance_variable_satisfies_the_server_requirement(runner, monkeypatch):
    monkeypatch.setenv("GLEAN_INSTANCE", "acme")
    monkeypatch.setenv("GLEAN_INDEXING_API_TOKEN", "t")
    assert missing_credentials() == []


def test_project_requirement_blocks_outside_a_project(runner, ran, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(_build(ran, project=True), ["--output", "json"])
    assert result.exit_code == EXIT_PRECONDITION
    error = json.loads(result.output)["error"]
    assert error["code"] == "no_project"
    assert error["searched"]
    assert ran == []


def test_project_requirement_passes_inside_a_project(runner, ran, tmp_path, monkeypatch):
    (tmp_path / PROJECT_FILE).write_text("connector_name: wiki\n")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(_build(ran, project=True), ["--output", "json"])
    assert result.exit_code == EXIT_OK
    assert ran == [True]


def test_project_option_locates_a_project_elsewhere(runner, ran, tmp_path, monkeypatch):
    project = tmp_path / "connector"
    project.mkdir()
    (project / PROJECT_FILE).write_text("connector_name: wiki\n")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    result = runner.invoke(
        _build(ran, project=True), ["--project", str(project), "--output", "json"]
    )
    assert result.exit_code == EXIT_OK
    assert ran == [True]


def test_credentials_are_checked_before_the_project(runner, ran, tmp_path, monkeypatch):
    """Cheapest check first: a missing token needs no filesystem work, and is the
    likelier problem, so it should be what the operator is told about."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(_build(ran, credentials=True, project=True), ["--output", "json"])
    assert json.loads(result.output)["error"]["code"] == "missing_credentials"
    assert ran == []
