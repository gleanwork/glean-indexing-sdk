"""Tests for end-to-end document indexing waits."""

from unittest.mock import Mock, call, patch

import httpx
import pytest

from glean.api_client.errors import GleanError as ApiGleanError
from glean.api_client.models import (
    DebugDocumentResponse,
    DebugDocumentsResponse,
    DebugDocumentsResponseItem,
    DocumentDefinition,
    DocumentStatusResponse,
)
from glean.indexing.push import PushUploader
from glean.indexing.testing import mock_glean_client
from glean.indexing.testing.harness.indexing_wait import (
    IndexingWaitResult,
    capture_document_uploads,
    wait_for_documents_to_index,
)


def _document(document_id: str = "doc-1") -> DocumentDefinition:
    return DocumentDefinition(
        datasource="test_datasource",
        id=document_id,
        object_type="Article",
        title=f"Doc {document_id}",
    )


def _status(indexing_status: str) -> DebugDocumentsResponse:
    return DebugDocumentsResponse(
        document_statuses=[
            DebugDocumentsResponseItem(
                doc_id="doc-1",
                object_type="Article",
                debug_info=DebugDocumentResponse(
                    status=DocumentStatusResponse(indexing_status=indexing_status)
                ),
            )
        ]
    )


def test_capture_document_uploads_records_incremental_and_bulk_documents():
    incremental = _document("doc-1")
    bulk = _document("doc-2")
    uploader = PushUploader(datasource="test_datasource")

    with mock_glean_client():
        with capture_document_uploads() as captured:
            uploader.index_documents([incremental])
            uploader.bulk_index_documents([bulk])

    assert captured == [incremental, bulk]


@patch("glean.indexing.testing.indexing_status.time.sleep")
@patch("glean.indexing.testing.harness.indexing_wait.PushUploader.process_all_documents")
@patch("glean.indexing.testing.indexing_status.StatusClient.get_documents_status")
@patch("glean.indexing.testing.harness.indexing_wait.logger")
def test_already_indexed_skips_process_all(
    logger: Mock,
    get_status: Mock,
    process_all: Mock,
    sleep: Mock,
):
    get_status.return_value = _status("INDEXED")

    result = wait_for_documents_to_index(
        "test_datasource",
        [_document(), _document()],
    )

    assert result is IndexingWaitResult.INDEXED
    logger.warning.assert_not_called()
    sleep.assert_called_once_with(45)
    process_all.assert_not_called()


@patch("glean.indexing.testing.indexing_status.time.sleep")
@patch("glean.indexing.testing.harness.indexing_wait.PushUploader.process_all_documents")
@patch("glean.indexing.testing.indexing_status.StatusClient.get_documents_status")
def test_pending_document_triggers_process_all_then_poll(
    get_status: Mock,
    process_all: Mock,
    sleep: Mock,
):
    get_status.side_effect = [_status("NOT_INDEXED"), _status("INDEXED")]

    result = wait_for_documents_to_index(
        "test_datasource",
        [_document()],
    )

    assert result is IndexingWaitResult.INDEXED
    process_all.assert_called_once_with()
    assert sleep.call_args_list == [call(45), call(30)]


@patch("glean.indexing.testing.indexing_status.time.sleep")
@patch("glean.indexing.testing.harness.indexing_wait.PushUploader.process_all_documents")
@patch("glean.indexing.testing.indexing_status.StatusClient.get_documents_status")
def test_process_all_rate_limit_is_ignored(
    get_status: Mock,
    process_all: Mock,
    _sleep: Mock,
):
    response = httpx.Response(429, request=httpx.Request("POST", "https://example.com"))
    process_all.side_effect = ApiGleanError("rate limited", response)
    get_status.side_effect = [_status("NOT_INDEXED"), _status("INDEXED")]

    result = wait_for_documents_to_index(
        "test_datasource",
        [_document()],
    )

    assert result is IndexingWaitResult.INDEXED
    process_all.assert_called_once_with()


@patch("glean.indexing.testing.indexing_status.time.sleep")
@patch("glean.indexing.testing.harness.indexing_wait.PushUploader.process_all_documents")
@patch("glean.indexing.testing.indexing_status.StatusClient.get_documents_status")
def test_process_all_non_rate_limit_error_is_raised(
    get_status: Mock,
    process_all: Mock,
    _sleep: Mock,
):
    response = httpx.Response(500, request=httpx.Request("POST", "https://example.com"))
    process_all.side_effect = ApiGleanError("server error", response)
    get_status.return_value = _status("NOT_INDEXED")

    with pytest.raises(ApiGleanError):
        wait_for_documents_to_index(
            "test_datasource",
            [_document()],
        )


@patch("glean.indexing.testing.indexing_status.POLL_TIMEOUT_SECONDS", 60)
@patch("glean.indexing.testing.indexing_status.time.sleep")
@patch("glean.indexing.testing.harness.indexing_wait.PushUploader.process_all_documents")
@patch("glean.indexing.testing.indexing_status.StatusClient.get_documents_status")
@patch("glean.indexing.testing.harness.indexing_wait.logger")
def test_polling_returns_pending_with_actionable_message(
    logger: Mock,
    get_status: Mock,
    process_all: Mock,
    sleep: Mock,
):
    get_status.return_value = _status("NOT_INDEXED")

    result = wait_for_documents_to_index(
        "test_datasource",
        [_document()],
    )

    assert result is IndexingWaitResult.PENDING
    assert (
        "queued for asynchronous indexing, which may take longer"
        in logger.warning.call_args.args[0]
    )
    process_all.assert_called_once_with()
    assert sleep.call_args_list == [call(45), call(30), call(30)]
    assert get_status.call_count == 3
