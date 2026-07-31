"""Tests for shared document indexing status checks."""

from unittest.mock import Mock, patch

from glean.api_client.models import (
    DebugDocumentRequest,
    DebugDocumentResponse,
    DebugDocumentsResponse,
    DebugDocumentsResponseItem,
    DocumentDefinition,
    DocumentStatusResponse,
)
from glean.indexing.testing.indexing_status import (
    IndexingWaitResult,
    check_documents_status,
    document_status_requests,
)


def _response(*, uploaded_at: str, indexed_at: str) -> DebugDocumentsResponse:
    return DebugDocumentsResponse(
        document_statuses=[
            DebugDocumentsResponseItem(
                object_type="Article",
                doc_id="doc-1",
                debug_info=DebugDocumentResponse(
                    status=DocumentStatusResponse(
                        upload_status="UPLOADED",
                        indexing_status="INDEXED",
                        permission_identity_status="UPLOADED",
                        last_uploaded_at=uploaded_at,
                        last_indexed_at=indexed_at,
                    )
                ),
            )
        ]
    )


def test_document_status_requests_deduplicates_and_skips_incomplete_documents():
    documents = [
        DocumentDefinition(
            datasource="wikipedia",
            id="doc-1",
            object_type="Article",
            title="One",
        ),
        DocumentDefinition(
            datasource="wikipedia",
            id="doc-1",
            object_type="Article",
            title="Duplicate",
        ),
        DocumentDefinition(datasource="wikipedia", id="doc-2", title="Missing type"),
    ]

    requests = document_status_requests(documents)

    assert requests == [DebugDocumentRequest(object_type="Article", doc_id="doc-1")]


@patch("glean.indexing.testing.indexing_status.StatusClient.get_documents_status")
def test_current_upload_is_indexed(get_status: Mock):
    get_status.return_value = _response(
        uploaded_at="2026-07-24T10:00:00Z",
        indexed_at="2026-07-24T10:01:00Z",
    )

    snapshot = check_documents_status(
        "wikipedia",
        [DebugDocumentRequest(object_type="Article", doc_id="doc-1")],
    )

    assert snapshot.result is IndexingWaitResult.INDEXED


@patch("glean.indexing.testing.indexing_status.StatusClient.get_documents_status")
def test_previous_index_does_not_satisfy_latest_upload(get_status: Mock):
    get_status.return_value = _response(
        uploaded_at="2026-07-24T10:01:00Z",
        indexed_at="2026-07-24T10:00:00Z",
    )

    snapshot = check_documents_status(
        "wikipedia",
        [DebugDocumentRequest(object_type="Article", doc_id="doc-1")],
    )

    assert snapshot.result is IndexingWaitResult.PENDING
