"""Shared document indexing status checks for the test harness and CLI."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from glean.api_client.models import (
    DebugDocumentRequest,
    DebugDocumentsResponse,
    DocumentDefinition,
)
from glean.indexing.push import StatusClient

POLL_INTERVAL_SECONDS = 30
POLL_TIMEOUT_SECONDS = 300


class IndexingWaitResult(str, Enum):
    """Outcome of checking whether uploaded documents finished indexing."""

    INDEXED = "indexed"
    PENDING = "pending"


@dataclass(frozen=True)
class IndexingStatusSnapshot:
    """Latest indexing outcome and raw document status response."""

    result: IndexingWaitResult
    response: DebugDocumentsResponse


def document_status_requests(
    documents: Sequence[DocumentDefinition],
) -> list[DebugDocumentRequest]:
    """Build deduplicated status requests for documents with stable identifiers."""
    requests: dict[tuple[str, str], DebugDocumentRequest] = {}
    for document in documents:
        if document.id and document.object_type:
            key = (document.object_type, document.id)
            requests[key] = DebugDocumentRequest(object_type=key[0], doc_id=key[1])
    return list(requests.values())


def check_documents_status(
    datasource: str,
    documents: Sequence[DebugDocumentRequest],
) -> IndexingStatusSnapshot:
    """Check document indexing status once."""
    response = StatusClient(datasource=datasource).get_documents_status(documents)
    expected = {(document.object_type, document.doc_id) for document in documents}
    indexed: set[tuple[str, str]] = set()

    for item in response.document_statuses or []:
        status = item.debug_info.status if item.debug_info else None
        if (
            item.object_type
            and item.doc_id
            and status
            and status.indexing_status == "INDEXED"
            and _is_latest_upload_indexed(status.last_uploaded_at, status.last_indexed_at)
        ):
            indexed.add((item.object_type, item.doc_id))

    result = IndexingWaitResult.INDEXED if expected <= indexed else IndexingWaitResult.PENDING
    return IndexingStatusSnapshot(result=result, response=response)


def poll_documents_status(
    datasource: str,
    documents: Sequence[DebugDocumentRequest],
    *,
    initial_wait_seconds: int = 0,
    on_pending: Callable[[], None] | None = None,
) -> IndexingStatusSnapshot:
    """Poll document status for up to five minutes using shared fixed defaults."""
    if initial_wait_seconds:
        time.sleep(initial_wait_seconds)

    snapshot = check_documents_status(datasource, documents)
    if snapshot.result is IndexingWaitResult.INDEXED:
        return snapshot

    if on_pending:
        on_pending()

    poll_count = POLL_TIMEOUT_SECONDS // POLL_INTERVAL_SECONDS
    for _ in range(poll_count):
        time.sleep(POLL_INTERVAL_SECONDS)
        snapshot = check_documents_status(datasource, documents)
        if snapshot.result is IndexingWaitResult.INDEXED:
            return snapshot

    return snapshot


def _is_latest_upload_indexed(
    last_uploaded_at: str | None,
    last_indexed_at: str | None,
) -> bool:
    """Return whether indexing is at least as recent as the latest upload."""
    if not last_uploaded_at:
        return True
    if not last_indexed_at:
        return False

    uploaded = _parse_timestamp(last_uploaded_at)
    indexed = _parse_timestamp(last_indexed_at)
    if uploaded is None or indexed is None:
        return last_indexed_at >= last_uploaded_at
    return indexed >= uploaded


def _parse_timestamp(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
