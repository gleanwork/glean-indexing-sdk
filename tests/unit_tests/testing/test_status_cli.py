"""Tests for the document indexing status CLI."""

from unittest.mock import Mock, patch

from click.testing import CliRunner
from glean.api_client.models import (
    DebugDocumentResponse,
    DebugDocumentsResponse,
    DebugDocumentsResponseItem,
    DocumentStatusResponse,
)

from glean.indexing.testing.indexing_status import (
    IndexingStatusSnapshot,
    IndexingWaitResult,
)
from glean.indexing.testing.status_cli import cli


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


@patch("glean.indexing.testing.status_cli.check_documents_status")
def test_single_check_uses_shared_status_checker(check_status: Mock):
    check_status.return_value = _snapshot(IndexingWaitResult.INDEXED)

    result = CliRunner().invoke(
        cli,
        ["--datasource", "wikipedia", "--document", "Article", "doc-1"],
    )

    assert result.exit_code == 0
    assert "Result: INDEXED" in result.output
    requests = check_status.call_args.args[1]
    assert [(request.object_type, request.doc_id) for request in requests] == [("Article", "doc-1")]


@patch("glean.indexing.testing.status_cli.poll_documents_status")
def test_poll_mode_uses_shared_poller(poll_status: Mock):
    poll_status.return_value = _snapshot(IndexingWaitResult.PENDING)

    result = CliRunner().invoke(
        cli,
        ["--datasource", "wikipedia", "--document", "Article", "doc-1", "--poll"],
    )

    assert result.exit_code == 0
    assert "Result: PENDING" in result.output
    assert "still queued for asynchronous indexing" in result.output
    poll_status.assert_called_once()
