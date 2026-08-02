"""Tests for `glean-idx datasource`.

`teardown` gets the most attention: emptying a datasource is expressed as an
empty bulk upload, so the flags on that one call are the whole behaviour.
"""

import json
import textwrap
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from glean.api_client.models import (
    CustomDatasourceConfig,
    DatasourceObjectTypeDocumentCountEntry,
)
from glean.indexing.cli.commands.datasource import datasource
from glean.indexing.cli.errors import EXIT_PRECONDITION, EXIT_REMOTE
from glean.indexing.cli.project import PROJECT_FILE


@pytest.fixture()
def credentials(monkeypatch):
    """Satisfy the credentials precondition these commands declare."""
    monkeypatch.setenv("GLEAN_SERVER_URL", "https://acme-be.glean.com")
    monkeypatch.setenv("GLEAN_INDEXING_API_TOKEN", "token")


def _entry(object_type: str, count: int) -> DatasourceObjectTypeDocumentCountEntry:
    return DatasourceObjectTypeDocumentCountEntry(object_type=object_type, count=count)


def _status_response(*, uploaded: int = 3, indexed: int = 3) -> Mock:
    """A status response shaped like the real one, without building the model tree."""
    return Mock(
        datasource_visibility=Mock(value="VISIBLE_TO_ALL"),
        documents=Mock(
            counts=Mock(
                uploaded=[_entry("Article", uploaded)],
                indexed=[_entry("Article", indexed)],
            ),
            bulk_upload_history=[
                Mock(
                    start_time="2026-01-01T00:00:00Z",
                    end_time="2026-01-01T00:01:00Z",
                    upload_id="older",
                    status=Mock(value="SUCCESS"),
                    processing_state=None,
                ),
                Mock(
                    start_time="2026-02-01T00:00:00Z",
                    end_time="2026-02-01T00:01:00Z",
                    upload_id="newest",
                    status=Mock(value="SUCCESS"),
                    processing_state=None,
                ),
            ],
            processing_history=[],
        ),
        identity=Mock(
            users=Mock(counts=Mock(uploaded=7)),
            groups=Mock(counts=Mock(uploaded=2)),
            memberships=Mock(counts=Mock(uploaded=9)),
            processing_history=[],
        ),
    )


# --- status ---------------------------------------------------------------


@patch("glean.indexing.push.StatusClient")
def test_status_reports_counts_and_identity(status_client: Mock, credentials):
    status_client.return_value.get_datasource_status.return_value = _status_response()
    result = CliRunner().invoke(datasource, ["status", "--datasource", "wiki", "--output", "json"])

    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data["visibility"] == "VISIBLE_TO_ALL"
    assert data["documents"]["uploaded"] == {"Article": 3}
    assert data["documents"]["indexed"] == {"Article": 3}
    assert data["identity"] == {"users": 7, "groups": 2, "memberships": 9, "last_processing": None}


@patch("glean.indexing.push.StatusClient")
def test_status_picks_the_newest_upload_regardless_of_order(status_client: Mock, credentials):
    """History arrives without a documented order, so the latest is chosen by time."""
    status_client.return_value.get_datasource_status.return_value = _status_response()
    result = CliRunner().invoke(datasource, ["status", "--datasource", "wiki", "--output", "json"])

    latest = json.loads(result.output)["data"]["documents"]["last_bulk_upload"]
    assert latest["upload_id"] == "newest"


@patch("glean.indexing.push.StatusClient")
def test_status_calls_out_uploaded_but_unindexed(status_client: Mock, credentials):
    """The gap this command exists to surface."""
    status_client.return_value.get_datasource_status.return_value = _status_response(indexed=0)
    result = CliRunner().invoke(datasource, ["status", "--datasource", "wiki", "--output", "text"])

    assert result.exit_code == 0
    assert "uploaded but none are indexed" in result.output
    assert "datasource process" in result.output


@patch("glean.indexing.push.StatusClient")
def test_status_survives_a_response_with_nothing_populated(status_client: Mock, credentials):
    status_client.return_value.get_datasource_status.return_value = Mock(
        documents=None, identity=None, datasource_visibility=None
    )
    result = CliRunner().invoke(datasource, ["status", "--datasource", "wiki", "--output", "text"])

    assert result.exit_code == 0
    assert "none reported" in result.output


@patch("glean.indexing.push.StatusClient")
def test_status_reports_a_remote_failure(status_client: Mock, credentials):
    status_client.return_value.get_datasource_status.side_effect = RuntimeError("403")
    result = CliRunner().invoke(datasource, ["status", "--datasource", "wiki", "--output", "json"])

    assert result.exit_code == EXIT_REMOTE
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert "403" in payload["error"]["detail"]


def test_status_requires_credentials(monkeypatch):
    monkeypatch.delenv("GLEAN_SERVER_URL", raising=False)
    monkeypatch.delenv("GLEAN_INSTANCE", raising=False)
    monkeypatch.delenv("GLEAN_INDEXING_API_TOKEN", raising=False)
    result = CliRunner().invoke(datasource, ["status", "--datasource", "wiki", "--output", "json"])

    assert result.exit_code == EXIT_PRECONDITION


# --- configure ------------------------------------------------------------

CONNECTOR_SOURCE = textwrap.dedent(
    """
    from glean.api_client.models import CustomDatasourceConfig, ObjectDefinition

    class WikiConnector:
        configuration = CustomDatasourceConfig(
            name="wiki",
            display_name="Company Wiki",
            datasource_category="PUBLISHED_CONTENT",
            object_definitions=[ObjectDefinition(name="Article")],
        )

    class NoConfigConnector:
        pass
    """
)


@pytest.fixture()
def project(tmp_path):
    """A connector project whose connector carries a real configuration."""
    (tmp_path / PROJECT_FILE).write_text(
        "connector_name: wiki\nconnector_module: connector\nconnector_class: WikiConnector\n"
    )
    (tmp_path / "connector.py").write_text(CONNECTOR_SOURCE)
    return tmp_path


@patch("glean.indexing.push.PushUploader")
def test_configure_registers_the_connectors_configuration(uploader: Mock, project, credentials):
    result = CliRunner().invoke(
        datasource, ["configure", "--project", str(project), "--output", "json"]
    )

    assert result.exit_code == 0, result.output
    uploader.assert_called_once_with(datasource="wiki")
    registered = uploader.return_value.configure_datasource.call_args.args[0]
    assert isinstance(registered, CustomDatasourceConfig)
    assert registered.name == "wiki"

    data = json.loads(result.output)["data"]
    assert data["datasource"] == "wiki"
    assert data["registered"] is True


@patch("glean.indexing.push.PushUploader")
def test_configure_show_does_not_call_glean(uploader: Mock, project, credentials):
    result = CliRunner().invoke(
        datasource, ["configure", "--project", str(project), "--show", "--output", "json"]
    )

    assert result.exit_code == 0, result.output
    uploader.return_value.configure_datasource.assert_not_called()
    assert json.loads(result.output)["data"]["registered"] is False


@patch("glean.indexing.push.PushUploader")
def test_configure_renders_the_object_types_it_would_register(uploader: Mock, project, credentials):
    result = CliRunner().invoke(
        datasource, ["configure", "--project", str(project), "--show", "--output", "text"]
    )

    assert result.exit_code == 0, result.output
    assert "Company Wiki" in result.output
    assert "Article" in result.output


@patch("glean.indexing.push.PushUploader")
def test_configure_accepts_a_connector_override(uploader: Mock, project, credentials):
    result = CliRunner().invoke(
        datasource,
        [
            "configure",
            "--project",
            str(project),
            "--connector",
            "connector:WikiConnector",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["datasource"] == "wiki"


@patch("glean.indexing.push.PushUploader")
def test_configure_explains_a_connector_without_a_configuration(
    uploader: Mock, project, credentials
):
    result = CliRunner().invoke(
        datasource,
        [
            "configure",
            "--project",
            str(project),
            "--connector",
            "connector:NoConfigConnector",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == EXIT_PRECONDITION
    message = json.loads(result.output)["error"]["message"]
    assert "does not define a datasource configuration" in message


def test_configure_without_a_project_says_where_it_looked(tmp_path, credentials):
    """The first command to depend on `requires(project=True)`."""
    result = CliRunner().invoke(
        datasource, ["configure", "--project", str(tmp_path), "--output", "json"]
    )

    assert result.exit_code == EXIT_PRECONDITION
    error = json.loads(result.output)["error"]
    assert PROJECT_FILE in error["message"] or PROJECT_FILE in (error.get("detail") or "")


# --- process --------------------------------------------------------------


@patch("glean.indexing.push.PushUploader")
def test_process_requests_a_run(uploader: Mock, credentials):
    result = CliRunner().invoke(datasource, ["process", "--datasource", "wiki", "--output", "json"])

    assert result.exit_code == 0
    uploader.return_value.process_all_documents.assert_called_once_with()
    assert json.loads(result.output)["data"] == {"datasource": "wiki", "requested": True}


@patch("glean.indexing.push.PushUploader")
def test_process_reports_a_remote_failure(uploader: Mock, credentials):
    uploader.return_value.process_all_documents.side_effect = RuntimeError("boom")
    result = CliRunner().invoke(datasource, ["process", "--datasource", "wiki", "--output", "json"])

    assert result.exit_code == EXIT_REMOTE


# --- teardown -------------------------------------------------------------


@patch("glean.indexing.push.PushUploader")
def test_teardown_uploads_one_empty_complete_page(uploader: Mock, credentials):
    """The mechanism: an empty upload marked complete, with the stale guard lifted.

    Every flag is load-bearing. Without `disable_stale_document_deletion_check`
    the API refuses the deletion; without `force_restart_upload` it can resume a
    previous upload rather than replacing its contents.
    """
    result = CliRunner().invoke(
        datasource, ["teardown", "--datasource", "wiki", "--yes", "--output", "json"]
    )

    assert result.exit_code == 0, result.output
    call = uploader.return_value.bulk_index_document_batches.call_args
    assert call.args[0] == [[]]
    assert call.kwargs == {
        "batch_count": 1,
        "force_restart_upload": True,
        "disable_stale_document_deletion_check": True,
    }
    assert json.loads(result.output)["data"] == {"datasource": "wiki", "emptied": True}


@patch("glean.indexing.push.PushUploader")
def test_teardown_requires_the_datasource_name_typed_back(uploader: Mock, credentials):
    result = CliRunner().invoke(
        datasource, ["teardown", "--datasource", "wiki", "--output", "text"], input="wiki\n"
    )

    assert result.exit_code == 0, result.output
    uploader.return_value.bulk_index_document_batches.assert_called_once()


@patch("glean.indexing.push.PushUploader")
def test_teardown_aborts_on_a_bare_confirmation(uploader: Mock, credentials):
    """`y` is not enough, which is the point of prompting for the name."""
    result = CliRunner().invoke(
        datasource, ["teardown", "--datasource", "wiki", "--output", "text"], input="y\n"
    )

    assert result.exit_code != 0
    uploader.return_value.bulk_index_document_batches.assert_not_called()


@patch("glean.indexing.push.PushUploader")
def test_teardown_aborts_on_the_wrong_name(uploader: Mock, credentials):
    result = CliRunner().invoke(
        datasource, ["teardown", "--datasource", "wiki", "--output", "text"], input="wikipedia\n"
    )

    assert result.exit_code != 0
    uploader.return_value.bulk_index_document_batches.assert_not_called()


@patch("glean.indexing.push.PushUploader")
def test_teardown_reports_a_remote_failure(uploader: Mock, credentials):
    uploader.return_value.bulk_index_document_batches.side_effect = RuntimeError("nope")
    result = CliRunner().invoke(
        datasource, ["teardown", "--datasource", "wiki", "--yes", "--output", "json"]
    )

    assert result.exit_code == EXIT_REMOTE


def test_an_empty_batch_reaches_the_api_as_a_complete_empty_upload():
    """Pins the library behaviour teardown depends on.

    `bulk_index_documents` returns early on an empty sequence, so teardown goes
    through the batch entry point instead. This asserts that path really does
    send `documents=[]` as both the first and the last page.
    """
    from glean.indexing.push import PushUploader

    client = MagicMock()

    class ClientContext:
        def __enter__(self):
            return client

        def __exit__(self, exc_type, exc, tb):
            return None

    with patch("glean.indexing.push.uploader.api_client", return_value=ClientContext()):
        PushUploader("wiki").bulk_index_document_batches(
            [[]],
            batch_count=1,
            force_restart_upload=True,
            disable_stale_document_deletion_check=True,
        )

    kwargs = client.indexing.documents.bulk_index.call_args.kwargs
    assert kwargs["documents"] == []
    assert kwargs["is_first_page"] is True
    assert kwargs["is_last_page"] is True
    assert kwargs["force_restart_upload"] is True
    assert kwargs["disable_stale_document_deletion_check"] is True


@patch("glean.indexing.push.PushUploader")
def test_configure_emits_snake_case_keys_and_only_declared_fields(
    uploader: Mock, project, credentials
):
    """`model_dump()` would return camelCase keys plus unset defaults.

    The rest of this CLI's JSON is snake_case, and an agent reading the payload
    should see what the connector declared rather than the model's defaults.
    """
    result = CliRunner().invoke(
        datasource, ["configure", "--project", str(project), "--show", "--output", "json"]
    )

    configuration = json.loads(result.output)["data"]["configuration"]
    assert set(configuration) == {
        "name",
        "display_name",
        "datasource_category",
        "object_definitions",
    }
    assert configuration["object_definitions"] == [{"name": "Article"}]
