"""Tests for `glean-idx run`.

The connector is a real module on disk imported through the project machinery,
rather than a patched object: how a connector gets constructed is most of what
this command does, and the deployed entrypoint constructs it the same way.
"""

import json
import textwrap

import pytest
from click.testing import CliRunner

from glean.indexing.cli.commands.run import run
from glean.indexing.cli.errors import EXIT_INTERNAL, EXIT_PRECONDITION
from glean.indexing.cli.project import PROJECT_FILE

CONNECTOR_SOURCE = textwrap.dedent(
    '''
    import json
    import logging
    from pathlib import Path

    logger = logging.getLogger("glean.test_connector")

    CALLS = Path(__file__).parent / "calls.json"


    class WikiConnector:
        """Records how it was invoked, the way a real connector would index."""

        name = "wiki"

        def index_data(self, mode=None, options=None):
            logger.info("connector is running")
            CALLS.write_text(
                json.dumps(
                    {
                        "mode": getattr(mode, "value", mode),
                        "force_restart": options.force_restart,
                        "disable_stale_deletion_check": options.disable_stale_deletion_check,
                        "upload_timeout_ms": options.upload_timeout_ms,
                        "document_batch_size_bytes": options.document_batch_size_bytes,
                        "upload_max_workers": options.upload_max_workers,
                    }
                )
            )


    class FailingConnector:
        name = "wiki"

        def index_data(self, mode=None, options=None):
            raise RuntimeError("the source API refused the request")


    class NeedsArguments:
        def __init__(self, name, data_client):
            self.name = name

        def index_data(self, mode=None, options=None):
            pass


    class NotAConnector:
        pass
    '''
)


@pytest.fixture()
def credentials(monkeypatch):
    monkeypatch.setenv("GLEAN_SERVER_URL", "https://acme-be.glean.com")
    monkeypatch.setenv("GLEAN_INDEXING_API_TOKEN", "token")


@pytest.fixture()
def project(tmp_path):
    """A connector project holding several connectors to run."""
    (tmp_path / PROJECT_FILE).write_text(
        "connector_name: wiki\nconnector_module: connector\nconnector_class: WikiConnector\n"
    )
    (tmp_path / "connector.py").write_text(CONNECTOR_SOURCE)
    return tmp_path


def invoke(project, *extra: str):
    return CliRunner().invoke(run, ["--project", str(project), *extra])


def calls(project) -> dict:
    return json.loads((project / "calls.json").read_text())


def test_runs_the_projects_connector(project, credentials):
    result = invoke(project, "--output", "json")

    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert data["connector"] == "WikiConnector"
    assert data["datasource"] == "wiki"
    assert data["mode"] == "full"
    assert calls(project)["mode"] == "full"


def test_defaults_to_a_full_crawl(project, credentials):
    """A project file with no indexing_mode still has to run something."""
    assert invoke(project).exit_code == 0
    assert calls(project)["mode"] == "full"


def test_takes_the_mode_from_the_project_file(project, credentials):
    (project / PROJECT_FILE).write_text(
        "connector_module: connector\nconnector_class: WikiConnector\nindexing_mode: incremental\n"
    )

    assert invoke(project).exit_code == 0
    assert calls(project)["mode"] == "incremental"


def test_the_mode_flag_overrides_the_project_file(project, credentials):
    (project / PROJECT_FILE).write_text(
        "connector_module: connector\nconnector_class: WikiConnector\nindexing_mode: incremental\n"
    )

    assert invoke(project, "--mode", "full").exit_code == 0
    assert calls(project)["mode"] == "full"


def test_upload_options_reach_the_connector(project, credentials):
    result = invoke(
        project,
        "--force-restart",
        "--disable-stale-deletion-check",
        "--upload-timeout-ms",
        "60000",
        "--batch-size-bytes",
        "1024",
        "--max-workers",
        "3",
    )

    assert result.exit_code == 0, result.output
    assert calls(project) == {
        "mode": "full",
        "force_restart": True,
        "disable_stale_deletion_check": True,
        "upload_timeout_ms": 60000,
        "document_batch_size_bytes": 1024,
        "upload_max_workers": 3,
    }


def test_unset_upload_options_keep_the_library_defaults(project, credentials):
    """Passing None through would override the defaults with nothing."""
    from glean.indexing.models import ConnectorOptions

    assert invoke(project).exit_code == 0
    recorded = calls(project)
    defaults = ConnectorOptions()
    assert recorded["document_batch_size_bytes"] == defaults.document_batch_size_bytes
    assert recorded["upload_max_workers"] == defaults.upload_max_workers
    assert recorded["upload_timeout_ms"] == defaults.upload_timeout_ms


def test_a_connector_reference_can_be_given_explicitly(project, credentials):
    result = invoke(project, "--connector", "connector:WikiConnector", "--output", "json")

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["connector"] == "WikiConnector"


# --- failure modes --------------------------------------------------------


def test_a_connector_needing_constructor_arguments_explains_the_contract(project, credentials):
    """The deployed entrypoint calls the class with no arguments, so this cannot work."""
    result = invoke(project, "--connector", "connector:NeedsArguments", "--output", "json")

    assert result.exit_code == EXIT_PRECONDITION
    error = json.loads(result.stdout)["error"]
    assert error["code"] == "connector_not_importable"
    assert "without arguments" in error["message"]
    assert "super().__init__" in error["detail"]


def test_an_object_without_index_data_is_rejected_before_running(project, credentials):
    result = invoke(project, "--connector", "connector:NotAConnector", "--output", "json")

    assert result.exit_code == EXIT_PRECONDITION
    error = json.loads(result.stdout)["error"]
    assert "no index_data method" in error["message"]
    assert "BaseDatasourceConnector" in error["detail"]


def test_a_failing_connector_reports_its_traceback(project, credentials):
    """The traceback is the only thing that makes a failed run debuggable."""
    result = invoke(project, "--connector", "connector:FailingConnector", "--output", "json")

    assert result.exit_code == EXIT_INTERNAL
    error = json.loads(result.stdout)["error"]
    assert error["code"] == "connector_run_failed"
    assert error["data"]["error_type"] == "RuntimeError"
    assert "the source API refused the request" in error["data"]["error"]
    assert "Traceback" in error["detail"]
    assert "raise RuntimeError" in error["detail"]


def test_a_failing_connector_points_at_the_status_command(project, credentials):
    result = invoke(project, "--connector", "connector:FailingConnector", "--output", "json")

    hints = " ".join(json.loads(result.stdout)["error"]["hint"])
    assert "datasource status" in hints


def test_running_without_a_project_fails_before_importing_anything(tmp_path, credentials):
    result = CliRunner().invoke(run, ["--project", str(tmp_path), "--output", "json"])

    assert result.exit_code == EXIT_PRECONDITION
    assert json.loads(result.stdout)["error"]["code"] == "no_project"


def test_running_without_credentials_fails_before_importing_anything(project, monkeypatch):
    monkeypatch.delenv("GLEAN_SERVER_URL", raising=False)
    monkeypatch.delenv("GLEAN_INSTANCE", raising=False)
    monkeypatch.delenv("GLEAN_INDEXING_API_TOKEN", raising=False)

    result = invoke(project, "--output", "json")

    assert result.exit_code == EXIT_PRECONDITION
    assert not (project / "calls.json").exists()


# --- output integrity -----------------------------------------------------


def test_connector_logging_does_not_corrupt_the_json_envelope(project, credentials):
    """The connector logs while running, and stdout carries one JSON document.

    `setup_connector_logging` attaches a stdout handler by default, which would
    interleave log lines with the envelope and make it unparseable.
    """
    result = CliRunner().invoke(run, ["--project", str(project), "--output", "json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)  # would raise if logs were interleaved
    assert payload["ok"] is True
    assert "connector is running" in result.stderr


def test_text_output_also_keeps_logs_off_stdout(project, credentials):
    result = CliRunner().invoke(run, ["--project", str(project), "--output", "text"])

    assert result.exit_code == 0, result.output
    assert "Ran WikiConnector against wiki" in result.stdout
    assert "connector is running" not in result.stdout
