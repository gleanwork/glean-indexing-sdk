"""`glean-idx doctor` behaviour, including its exit contract."""

import json

import pytest
from click.testing import CliRunner

from glean.indexing.cli.errors import EXIT_OK, EXIT_PRECONDITION, EXIT_REMOTE
from glean.indexing.cli.main import cli
from glean.indexing.cli.output import set_output_mode

ENV_VARS = ("GLEAN_SERVER_URL", "GLEAN_INSTANCE", "GLEAN_INDEXING_API_TOKEN")


@pytest.fixture()
def runner(monkeypatch):
    """A runner with the Glean environment cleared.

    Every test here needs both, and the recorded output mode is process-wide,
    so resetting it alongside keeps invocations independent.
    """
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    set_output_mode(None)
    return CliRunner()


def _credentials(monkeypatch):
    monkeypatch.setenv("GLEAN_SERVER_URL", "https://acme-be.glean.com")
    monkeypatch.setenv("GLEAN_INDEXING_API_TOKEN", "token-value")


def test_reports_ready_when_both_variables_are_set(runner, monkeypatch):
    _credentials(monkeypatch)
    result = runner.invoke(cli, ["doctor", "--output", "json"])
    assert result.exit_code == EXIT_OK
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["ready"] is True


def test_missing_credentials_is_a_precondition_failure(runner):
    result = runner.invoke(cli, ["doctor", "--output", "json"])
    assert result.exit_code == EXIT_PRECONDITION
    payload = json.loads(result.output)
    # `ok` has to mean "achieved its purpose" for agents to branch on it.
    assert payload["ok"] is False
    assert payload["error"]["code"] == "missing_credentials"
    assert payload["error"]["data"]["ready"] is False


def test_failure_still_reports_every_check_it_made(runner):
    result = runner.invoke(cli, ["doctor", "--output", "json"])
    names = [c["name"] for c in json.loads(result.output)["error"]["data"]["checks"]]
    assert names == ["GLEAN_SERVER_URL", "GLEAN_INDEXING_API_TOKEN"]


def test_never_echoes_the_token(runner, monkeypatch):
    _credentials(monkeypatch)
    result = runner.invoke(cli, ["doctor", "--output", "json"])
    assert "token-value" not in result.output
    assert "set (11 chars)" in result.output


def test_legacy_instance_variable_is_accepted_but_flagged(runner, monkeypatch):
    monkeypatch.setenv("GLEAN_INSTANCE", "acme")
    monkeypatch.setenv("GLEAN_INDEXING_API_TOKEN", "token-value")
    result = runner.invoke(cli, ["doctor", "--output", "json"])
    assert result.exit_code == EXIT_OK
    check = json.loads(result.output)["data"]["checks"][0]
    assert "deprecated" in check["note"]


def test_global_flag_is_accepted_before_the_subcommand(runner, monkeypatch):
    _credentials(monkeypatch)
    result = runner.invoke(cli, ["--output", "json", "doctor"])
    assert result.exit_code == EXIT_OK
    assert json.loads(result.output)["ok"] is True


def test_probe_failure_is_a_remote_error(runner, monkeypatch):
    _credentials(monkeypatch)

    class Boom:
        def __init__(self, **_kwargs):
            pass

        def get_datasource_status(self):
            raise RuntimeError("401 unauthorized")

    monkeypatch.setattr("glean.indexing.push.StatusClient", Boom)
    result = runner.invoke(cli, ["doctor", "--datasource", "wiki", "--output", "json"])
    assert result.exit_code == EXIT_REMOTE
    error = json.loads(result.output)["error"]
    assert error["code"] == "remote_error"
    assert "401 unauthorized" in error["detail"]


def test_probe_success_is_reported_as_a_check(runner, monkeypatch):
    _credentials(monkeypatch)

    class Fine:
        def __init__(self, **_kwargs):
            pass

        def get_datasource_status(self):
            return {"documentCount": 3}

    monkeypatch.setattr("glean.indexing.push.StatusClient", Fine)
    result = runner.invoke(cli, ["doctor", "--datasource", "wiki", "--output", "json"])
    assert result.exit_code == EXIT_OK
    names = [c["name"] for c in json.loads(result.output)["data"]["checks"]]
    assert "datasource:wiki" in names
