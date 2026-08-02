"""Tests for `glean-idx test`.

The connector is a real `BaseDatasourceConnector` on disk, because the harness
type-checks its argument and auto-discovering data clients depends on how a real
connector stores them.
"""

import json
import textwrap

import pytest
from click.testing import CliRunner

from glean.indexing.cli.commands.test import PHASES, test as test_command
from glean.indexing.cli.errors import EXIT_PRECONDITION, EXIT_VALIDATION
from glean.indexing.cli.project import PROJECT_FILE

CONNECTOR_SOURCE = textwrap.dedent(
    '''
    from glean.api_client.models import CustomDatasourceConfig, DocumentDefinition
    from glean.indexing.connectors import BaseDatasourceConnector
    from glean.indexing.testing import StaticDataClient

    RECORDS = [{"id": "1", "title": "Alpha"}, {"id": "2", "title": "Beta"}]


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
    return tmp_path


@pytest.fixture()
def no_credentials(monkeypatch):
    for name in ("GLEAN_SERVER_URL", "GLEAN_INSTANCE", "GLEAN_INDEXING_API_TOKEN"):
        monkeypatch.delenv(name, raising=False)


def invoke(project, *extra: str):
    return CliRunner().invoke(test_command, ["--project", str(project), *extra])


def test_phase_one_posts_the_transformed_documents(project, no_credentials):
    result = invoke(project, "--output", "json")

    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert data["phase"] == 1
    assert data["fidelity"] == PHASES[1]
    assert data["posted"] == {"documents": 2}


def test_phase_one_needs_no_credentials(project, no_credentials):
    """Glean is mocked in phase 1, so demanding a token would block it for nothing."""
    assert invoke(project).exit_code == 0


def test_phase_three_requires_credentials(project, no_credentials):
    result = invoke(project, "--phase", "3", "--output", "json")

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
    assert "Nothing was posted" in result.stdout


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
    (project / "testing_config.yaml").write_text("testing:\n  cache_dir: .custom_cache/\n")

    assert invoke(project).exit_code == 0


def test_running_without_a_project_fails_before_importing(tmp_path, no_credentials):
    result = CliRunner().invoke(test_command, ["--project", str(tmp_path), "--output", "json"])

    assert result.exit_code == EXIT_PRECONDITION
    assert json.loads(result.stdout)["error"]["code"] == "no_project"
