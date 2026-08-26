"""Tests for `glean-idx test`.

The connector is a real `BaseDatasourceConnector` on disk, because the harness
type-checks its argument and auto-discovering data clients depends on how a real
connector stores them.
"""

import json
import textwrap
from types import SimpleNamespace
from typing import Optional

import pytest
from click.testing import CliRunner

from glean.indexing.cli.commands.test import PHASES
from glean.indexing.cli.commands.test import test as test_command
from glean.indexing.cli.errors import EXIT_PRECONDITION, EXIT_VALIDATION
from glean.indexing.cli.project import PROJECT_FILE

CONNECTOR_SOURCE = textwrap.dedent(
    '''
    from glean.api_client.models import CustomDatasourceConfig, DocumentDefinition
    from glean.indexing.connectors import BaseDatasourceConnector
    from glean.indexing.testing import StaticDataClient

    RECORDS = [{"id": str(n), "title": f"Page {n}"} for n in range(1, 21)]


    class WikiConnector(BaseDatasourceConnector):
        configuration = CustomDatasourceConfig(name="wiki", display_name="Wiki")

        def __init__(self):
            super().__init__("wiki", StaticDataClient(RECORDS))

        def transform(self, data):
            return [
                DocumentDefinition(datasource="wiki", id=record["id"], title=record["title"])
                for record in data
            ]


    class EmptyConnector(BaseDatasourceConnector):
        configuration = CustomDatasourceConfig(name="wiki", display_name="Wiki")

        def __init__(self):
            super().__init__("wiki", StaticDataClient([]))

        def transform(self, data):
            return []


    class ExplodingConnector(BaseDatasourceConnector):
        configuration = CustomDatasourceConfig(name="wiki", display_name="Wiki")

        def __init__(self):
            super().__init__("wiki", StaticDataClient(RECORDS))

        def transform(self, data):
            raise ValueError("the title field is missing")


    class HandRolled:
        """Not a BaseConnector, so the harness cannot take it."""

        name = "wiki"

        def index_data(self, mode=None, options=None):
            pass
    '''
)


@pytest.fixture()
def project(tmp_path):
    (tmp_path / PROJECT_FILE).write_text(
        "connector_name: wiki\nconnector_module: connector\nconnector_class: WikiConnector\n"
    )
    (tmp_path / "connector.py").write_text(CONNECTOR_SOURCE)
    # `cache_dir` defaults to a cwd-relative path, so without this the
    # integration phase records fixtures into the repository it is run from.
    (tmp_path / "testing_config.yaml").write_text(
        f"testing:\n  cache_dir: {tmp_path / '.cache'}/\n"
    )
    return tmp_path


@pytest.fixture()
def no_credentials(monkeypatch):
    for name in ("GLEAN_SERVER_URL", "GLEAN_INSTANCE", "GLEAN_INDEXING_API_TOKEN"):
        monkeypatch.delenv(name, raising=False)


def invoke(project, *extra: str, input: Optional[str] = None):
    return CliRunner().invoke(test_command, ["--project", str(project), *extra], input=input)


def test_the_mock_phase_posts_the_transformed_documents(project, no_credentials):
    result = invoke(project, "--output", "json")

    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert [entry["phase"] for entry in data["phases"]] == ["mock"]
    mock_phase = data["phases"][0]
    assert mock_phase["status"] == "ran"
    assert mock_phase["fidelity"] == PHASES["mock"]["summary"]
    assert mock_phase["posted"] == {"documents": 20}


def test_the_mock_phase_needs_no_credentials(project, no_credentials):
    """Glean is mocked, so demanding a token would block the cheapest check."""
    assert invoke(project).exit_code == 0


def test_the_live_phase_requires_credentials(project, no_credentials):
    result = invoke(project, "--phase", "live", "--output", "json")

    assert result.exit_code == EXIT_PRECONDITION
    assert json.loads(result.stdout)["error"]["code"] == "missing_credentials"


def test_the_discovered_data_clients_are_reported(project, no_credentials):
    """The harness needs this mapping, so the caller should see what was found."""
    result = invoke(project, "--output", "json")

    assert json.loads(result.stdout)["data"]["clients"] == ["data_client"]


def test_a_connector_posting_nothing_is_called_out(project, no_credentials):
    """Zero documents is a silent failure otherwise: it exits 0 and indexes nothing."""
    result = invoke(project, "--connector", "connector:EmptyConnector", "--output", "text")

    assert result.exit_code == 0
    assert "posted nothing" in result.stdout


def test_a_failing_transform_reports_the_cause(project, no_credentials):
    result = invoke(project, "--connector", "connector:ExplodingConnector", "--output", "json")

    assert result.exit_code == EXIT_VALIDATION
    error = json.loads(result.stdout)["error"]
    assert error["data"]["error_type"] == "ValueError"
    assert "the title field is missing" in error["detail"]


def test_a_connector_the_harness_cannot_take_says_so(project, no_credentials):
    result = invoke(project, "--connector", "connector:HandRolled", "--output", "json")

    assert result.exit_code == EXIT_VALIDATION
    error = json.loads(result.stdout)["error"]
    assert "cannot be tested by the harness" in error["message"]
    assert "glean-idx run" in " ".join(error["hint"])


def test_the_mode_comes_from_the_project_file(project, no_credentials):
    (project / PROJECT_FILE).write_text(
        "connector_module: connector\nconnector_class: WikiConnector\nindexing_mode: incremental\n"
    )

    result = invoke(project, "--output", "json")

    assert json.loads(result.stdout)["data"]["mode"] == "incremental"


def test_a_missing_explicit_config_is_an_error(project, no_credentials):
    """Silently falling back would run with settings the caller did not ask for."""
    result = invoke(project, "--config", str(project / "absent.yaml"), "--output", "json")

    assert result.exit_code == EXIT_VALIDATION
    assert "no harness config" in json.loads(result.stdout)["error"]["message"]


def test_the_projects_config_file_is_picked_up(project, no_credentials):
    (project / "testing_config.yaml").write_text(
        f"testing:\n  cache_dir: {project / '.custom'}/\n  run_id_prefix: custom\n"
    )

    assert invoke(project).exit_code == 0


def test_running_without_a_project_fails_before_importing(tmp_path, no_credentials):
    result = CliRunner().invoke(test_command, ["--project", str(tmp_path), "--output", "json"])

    assert result.exit_code == EXIT_PRECONDITION
    assert json.loads(result.stdout)["error"]["code"] == "no_project"


def test_every_phase_name_maps_to_a_real_harness_method():
    """A typo in the table would only fail when someone chose that phase."""
    from glean.indexing.testing.harness import TestHarness

    for name, phase in PHASES.items():
        assert hasattr(TestHarness, phase["method"]), name
        assert hasattr(TestHarness, f"{phase['method']}_async"), name


def test_phase_numbers_are_rejected_with_the_valid_names(project, no_credentials):
    """Anyone arriving from the SDK's "Phase 2" wording should be redirected."""
    result = invoke(project, "--phase", "2")

    assert result.exit_code != 0
    assert "mock" in result.output and "integration" in result.output and "live" in result.output


# --- --phase all ----------------------------------------------------------


def test_all_skips_live_without_credentials_rather_than_failing(project, no_credentials):
    """The workflow reports live as skipped; the earlier phases still hold information."""
    result = invoke(project, "--phase", "all", "--output", "json")

    assert result.exit_code == 0, result.output
    phases = {entry["phase"]: entry for entry in json.loads(result.stdout)["data"]["phases"]}
    assert phases["mock"]["status"] == "ran"
    assert phases["integration"]["status"] == "ran"
    assert phases["live"]["status"] == "skipped"
    assert "GLEAN_SERVER_URL" in phases["live"]["reason"]


def test_a_skipped_phase_is_stated_not_glossed_over(project, no_credentials):
    """A batch that quietly stepped over live would read as a clean end-to-end pass."""
    result = invoke(project, "--phase", "all", "--output", "text")

    assert "Skipped: live" in result.stdout
    assert "prove nothing" in result.stdout


def test_all_runs_every_phase_when_credentials_are_present(project, monkeypatch):
    from glean.indexing.testing.harness import TestHarness

    monkeypatch.setenv("GLEAN_SERVER_URL", "https://acme-be.glean.com")
    monkeypatch.setenv("GLEAN_INDEXING_API_TOKEN", "token")
    monkeypatch.setattr(
        TestHarness, "run_end_to_end", lambda self, **kwargs: SimpleNamespace(value="INDEXED")
    )

    result = invoke(project, "--phase", "all", "--yes", "--output", "json")

    assert result.exit_code == 0, result.output
    phases = json.loads(result.stdout)["data"]["phases"]
    assert [entry["status"] for entry in phases] == ["ran", "ran", "ran"]
    assert phases[-1]["indexing_result"] == "INDEXED"


def test_all_stops_at_the_first_failure(project, no_credentials):
    """A later phase cannot pass when an earlier one failed, and live would upload it."""
    result = invoke(
        project, "--phase", "all", "--connector", "connector:ExplodingConnector", "--output", "json"
    )

    assert result.exit_code == EXIT_VALIDATION
    phases = json.loads(result.stdout)["error"]["data"]["phases"]
    assert [entry["phase"] for entry in phases] == ["mock"]
    assert phases[0]["status"] == "failed"
    assert phases[0]["error_type"] == "ValueError"


# --- live confirmation ------------------------------------------------------


def test_live_asks_for_confirmation_before_uploading(project, monkeypatch):
    """A misconfigured GLEAN_SERVER_URL should not upload real documents unnoticed."""
    monkeypatch.setenv("GLEAN_SERVER_URL", "https://acme-be.glean.com")
    monkeypatch.setenv("GLEAN_INDEXING_API_TOKEN", "token")

    result = invoke(project, "--phase", "live", "--output", "json", input="n\n")

    assert result.exit_code != 0
    assert result.output.startswith(
        "The live phase uploads real documents to Glean at 'https://acme-be.glean.com'"
    )


def test_yes_skips_the_live_confirmation_prompt(project, monkeypatch):
    """--yes is required for unattended use, so it must not hang on the prompt."""
    from glean.indexing.testing.harness import TestHarness

    monkeypatch.setenv("GLEAN_SERVER_URL", "https://acme-be.glean.com")
    monkeypatch.setenv("GLEAN_INDEXING_API_TOKEN", "token")
    monkeypatch.setattr(
        TestHarness, "run_end_to_end", lambda self, **kwargs: SimpleNamespace(value="INDEXED")
    )

    result = invoke(project, "--phase", "live", "--yes", "--output", "json")

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["phases"][0]["indexing_result"] == "INDEXED"


def test_confirming_the_live_prompt_passes_confirm_to_the_harness(project, monkeypatch):
    """The CLI's own prompt stands in for the harness's confirm=True guard."""
    from glean.indexing.testing.harness import TestHarness

    monkeypatch.setenv("GLEAN_SERVER_URL", "https://acme-be.glean.com")
    monkeypatch.setenv("GLEAN_INDEXING_API_TOKEN", "token")

    seen_kwargs = {}

    def fake_run_end_to_end(self, **kwargs):
        seen_kwargs.update(kwargs)
        return SimpleNamespace(value="INDEXED")

    monkeypatch.setattr(TestHarness, "run_end_to_end", fake_run_end_to_end)

    result = invoke(project, "--phase", "live", "--output", "json", input="y\n")

    assert result.exit_code == 0, result.output
    assert seen_kwargs["confirm"] is True


def test_a_batch_does_not_prompt_when_live_will_be_skipped(project, no_credentials):
    """Confirming an upload that cannot happen would be a pointless interruption."""
    result = invoke(project, "--phase", "all", "--output", "json")

    assert result.exit_code == 0, result.output


def test_a_batch_skips_integration_when_there_is_nothing_to_record():
    """Directly, because a BaseDatasourceConnector always holds a data client."""
    from glean.indexing.cli.commands.test import INTEGRATION, _skip_reason

    assert _skip_reason(INTEGRATION, {}, "WikiConnector") is not None
    assert _skip_reason(INTEGRATION, {"data_client": object()}, "WikiConnector") is None


def test_asking_for_a_phase_that_cannot_run_is_still_an_error(project, no_credentials):
    """Skipping is a batch behaviour; an explicit request should not be silently ignored."""
    result = invoke(project, "--phase", "live", "--output", "json")

    assert result.exit_code == EXIT_PRECONDITION
    assert json.loads(result.stdout)["error"]["code"] == "missing_credentials"


def test_max_items_actually_caps_what_the_source_yields(project, no_credentials):
    """The harness looks each client up by attribute name.

    A cap stored under any other key is silently ignored, and a project with no
    config file has no client entries at all -- so this asserts on the resulting
    document count rather than on the config object, which would pass either way.
    """
    result = invoke(
        project, "--phase", "integration", "--refresh-cache", "--max-items", "4", "--output", "json"
    )

    assert result.exit_code == 0, result.output
    phase = json.loads(result.stdout)["data"]["phases"][0]
    assert phase["posted"] == {"documents": 4}


def test_max_items_must_be_positive(project, no_credentials):
    result = invoke(project, "--phase", "integration", "--max-items", "0")

    assert result.exit_code != 0
    assert "0 is not in the range" in result.output


def test_without_the_cap_the_harness_default_applies(project, no_credentials):
    """Pins the contrast: 20 records available, five taken."""
    result = invoke(project, "--phase", "integration", "--refresh-cache", "--output", "json")

    assert json.loads(result.stdout)["data"]["phases"][0]["posted"] == {"documents": 5}


def test_the_cap_reaches_clients_the_config_file_never_mentions(project, no_credentials):
    """The common case: a project whose config declares no clients at all."""
    from glean.indexing.cli.commands.test import _load_config

    config = _load_config(project, None, False, 7, ["data_client", "tickets_client"])

    assert config.clients["data_client"].max_items == 7
    assert config.clients["tickets_client"].max_items == 7
