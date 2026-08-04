"""Tests for `glean-idx document`."""

import json
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from glean.api_client.models import (
    DebugDocumentResponse,
    DebugDocumentsResponse,
    DebugDocumentsResponseItem,
    DocumentStatusResponse,
)
from glean.indexing.cli.commands.document import document
from glean.indexing.cli.errors import EXIT_PRECONDITION, EXIT_REMOTE
from glean.indexing.push.status import (
    IndexingStatusSnapshot,
    IndexingWaitResult,
)


@pytest.fixture()
def credentials(monkeypatch):
    """Satisfy the credentials precondition these commands declare."""
    monkeypatch.setenv("GLEAN_SERVER_URL", "https://acme-be.glean.com")
    monkeypatch.setenv("GLEAN_INDEXING_API_TOKEN", "token")


def _snapshot(result: IndexingWaitResult) -> IndexingStatusSnapshot:
    return IndexingStatusSnapshot(
        result=result,
        response=DebugDocumentsResponse(
            document_statuses=[
                DebugDocumentsResponseItem(
                    object_type="Article",
                    doc_id="doc-1",
                    debug_info=DebugDocumentResponse(
                        status=DocumentStatusResponse(
                            upload_status="UPLOADED",
                            indexing_status=result.value.upper(),
                            permission_identity_status="UPLOADED",
                        )
                    ),
                )
            ]
        ),
    )


@patch("glean.indexing.push.status.check_documents_status")
def test_single_check_uses_shared_status_checker(check_status: Mock, credentials):
    check_status.return_value = _snapshot(IndexingWaitResult.INDEXED)

    result = CliRunner().invoke(
        document,
        [
            "status",
            "--datasource",
            "wikipedia",
            "--document",
            "Article",
            "doc-1",
            "--output",
            "text",
        ],
    )

    assert result.exit_code == 0
    assert "Result: INDEXED" in result.output
    requests = check_status.call_args.args[1]
    assert [(request.object_type, request.doc_id) for request in requests] == [("Article", "doc-1")]


@patch("glean.indexing.push.status.poll_documents_status")
def test_poll_mode_uses_shared_poller(poll_status: Mock, credentials):
    poll_status.return_value = _snapshot(IndexingWaitResult.PENDING)

    result = CliRunner().invoke(
        document,
        [
            "status",
            "--datasource",
            "wikipedia",
            "--document",
            "Article",
            "doc-1",
            "--poll",
            "--output",
            "text",
        ],
    )

    assert result.exit_code == 0
    assert "Result: PENDING" in result.output
    assert "still queued for asynchronous indexing" in result.output
    poll_status.assert_called_once()


# --- status: envelope and preconditions -----------------------------------


@patch("glean.indexing.push.status.check_documents_status")
def test_status_emits_the_stable_envelope(check_status: Mock, credentials):
    check_status.return_value = _snapshot(IndexingWaitResult.INDEXED)
    result = CliRunner().invoke(
        document,
        [
            "status",
            "--datasource",
            "wikipedia",
            "--document",
            "Article",
            "doc-1",
            "--output",
            "json",
        ],
    )
    payload = json.loads(result.output)
    assert payload["ok"] is True
    entry = payload["data"]["documents"][0]
    # ids come off the response item; status fields off debug_info.status
    assert entry["object_type"] == "Article"
    assert entry["document_id"] == "doc-1"
    assert entry["permission_identity_status"] == "UPLOADED"


def test_status_without_credentials_is_a_precondition_failure(monkeypatch):
    for name in ("GLEAN_SERVER_URL", "GLEAN_INSTANCE", "GLEAN_INDEXING_API_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    result = CliRunner().invoke(
        document,
        [
            "status",
            "--datasource",
            "wikipedia",
            "--document",
            "Article",
            "doc-1",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == EXIT_PRECONDITION
    assert json.loads(result.output)["error"]["code"] == "missing_credentials"


@patch("glean.indexing.push.status.check_documents_status")
def test_remote_failure_carries_the_datasource(check_status: Mock, credentials):
    check_status.side_effect = RuntimeError("404 datasource not found")
    result = CliRunner().invoke(
        document,
        [
            "status",
            "--datasource",
            "wikipedia",
            "--document",
            "Article",
            "doc-1",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == EXIT_REMOTE
    error = json.loads(result.output)["error"]
    assert error["code"] == "remote_error"
    assert "404 datasource not found" in error["detail"]
    assert any("wikipedia" in hint for hint in error["hint"])


# --- access ---------------------------------------------------------------


@patch("glean.indexing.push.StatusClient")
def test_access_reports_the_verdict(status_client: Mock, credentials):
    status_client.return_value.check_document_access.return_value = Mock(has_access=False)
    result = CliRunner().invoke(
        document,
        [
            "access",
            "--datasource",
            "wiki",
            "--object-type",
            "Article",
            "--id",
            "doc-1",
            "--user",
            "contractor@example.com",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.output)["data"]["has_access"] is False


@patch("glean.indexing.push.StatusClient")
def test_access_text_names_the_user_and_document(status_client: Mock, credentials):
    status_client.return_value.check_document_access.return_value = Mock(has_access=True)
    result = CliRunner().invoke(
        document,
        [
            "access",
            "--datasource",
            "wiki",
            "--object-type",
            "Article",
            "--id",
            "doc-1",
            "--user",
            "jane@example.com",
            "--output",
            "text",
        ],
    )
    assert "jane@example.com can access Article/doc-1" in result.output


# --- delete ---------------------------------------------------------------


@patch("glean.indexing.push.PushUploader")
def test_delete_prompts_before_removing(uploader: Mock, credentials):
    result = CliRunner().invoke(
        document,
        ["delete", "--datasource", "wiki", "--document", "Article", "doc-1"],
        input="n\n",
    )
    assert result.exit_code != 0
    uploader.return_value.delete_document.assert_not_called()


@patch("glean.indexing.push.PushUploader")
def test_delete_yes_flag_makes_it_unattended(uploader: Mock, credentials):
    result = CliRunner().invoke(
        document,
        [
            "delete",
            "--datasource",
            "wiki",
            "--document",
            "Article",
            "doc-1",
            "--yes",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0
    uploader.return_value.delete_document.assert_called_once_with(
        object_type="Article", document_id="doc-1"
    )
    assert json.loads(result.output)["data"]["deleted"] == [
        {"object_type": "Article", "document_id": "doc-1"}
    ]


@patch("glean.indexing.push.PushUploader")
def test_delete_handles_several_documents(uploader: Mock, credentials):
    result = CliRunner().invoke(
        document,
        [
            "delete",
            "--datasource",
            "wiki",
            "--document",
            "Article",
            "doc-1",
            "--document",
            "Article",
            "doc-2",
            "--yes",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0
    assert len(json.loads(result.output)["data"]["deleted"]) == 2


# --- events --------------------------------------------------------------


@patch("glean.indexing.push.PushUploader")
def test_events_reports_no_events_readably(uploader: Mock, credentials):
    uploader.return_value.get_document_lifecycle_events.return_value = Mock(events=[])
    result = CliRunner().invoke(
        document,
        [
            "events",
            "--datasource",
            "wiki",
            "--object-type",
            "Article",
            "--id",
            "doc-1",
            "--output",
            "text",
        ],
    )
    assert result.exit_code == 0
    assert "No events." in result.output


@patch("glean.indexing.push.PushUploader")
def test_events_passes_through_the_optional_filters(uploader: Mock, credentials):
    uploader.return_value.get_document_lifecycle_events.return_value = Mock(events=[])
    CliRunner().invoke(
        document,
        [
            "events",
            "--datasource",
            "wiki",
            "--object-type",
            "Article",
            "--id",
            "doc-1",
            "--start-date",
            "2026-01-01",
            "--max-events",
            "5",
            "--output",
            "json",
        ],
    )
    uploader.return_value.get_document_lifecycle_events.assert_called_once_with(
        object_type="Article", document_id="doc-1", start_date="2026-01-01", max_events=5
    )


# --- global flags --------------------------------------------------------


# In a pipe the default output mode is JSON, so asking for text is what proves
# the flag reached the command rather than matching the default by accident.
SUBCOMMAND_ARGS = {
    "access": ["--object-type", "Article", "--id", "doc-1", "--user", "a@b.com"],
    "delete": ["--document", "Article", "doc-1", "--yes"],
    "events": ["--object-type", "Article", "--id", "doc-1"],
}


@pytest.mark.parametrize("subcommand", sorted(SUBCOMMAND_ARGS))
@patch("glean.indexing.push.PushUploader")
@patch("glean.indexing.push.StatusClient")
def test_output_text_is_honored_on_the_subcommand(
    status_client: Mock, uploader: Mock, subcommand: str, credentials
):
    uploader.return_value.get_document_lifecycle_events.return_value = Mock(events=[])
    result = CliRunner().invoke(
        document,
        [subcommand, "--datasource", "wiki", *SUBCOMMAND_ARGS[subcommand], "--output", "text"],
    )

    assert result.exit_code == 0
    assert not result.output.lstrip().startswith("{")


@patch("glean.indexing.push.PushUploader")
def test_assume_yes_is_honored_on_the_group(uploader: Mock, credentials):
    """`glean-idx --yes document delete` has to skip the prompt too."""
    from glean.indexing.cli.main import cli

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "document",
            "delete",
            "--datasource",
            "wiki",
            "--document",
            "Article",
            "doc-1",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0
    uploader.return_value.delete_document.assert_called_once()
