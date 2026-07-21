"""Document upload capture and indexing wait helpers for end-to-end tests."""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from unittest.mock import patch

from glean.api_client.errors import GleanError as ApiGleanError
from glean.api_client.models import DebugDocumentRequest, DebugDocumentsResponse, DocumentDefinition

from glean.indexing.push import PushUploader, StatusClient

logger = logging.getLogger(__name__)


@contextmanager
def capture_document_uploads() -> Iterator[list[DocumentDefinition]]:
    """Capture documents sent through ``PushUploader`` while preserving real uploads."""
    captured: list[DocumentDefinition] = []
    original_index = PushUploader.index_documents
    original_bulk_page = PushUploader.bulk_index_single_batch_upload

    def index_documents(
        uploader: PushUploader,
        documents: Sequence[DocumentDefinition],
        *,
        upload_id: str | None = None,
    ) -> None:
        document_list = list(documents)
        captured.extend(document_list)
        original_index(uploader, document_list, upload_id=upload_id)

    def bulk_index_single_batch_upload(
        uploader: PushUploader,
        documents: Sequence[DocumentDefinition],
        *,
        upload_id: str,
        is_first_page: bool | None = None,
        is_last_page: bool | None = None,
        batch_index: int = 0,
        batch_count: int = 1,
        force_restart_upload: bool | None = None,
        disable_stale_document_deletion_check: bool | None = None,
    ) -> None:
        document_list = list(documents)
        captured.extend(document_list)
        original_bulk_page(
            uploader,
            document_list,
            upload_id=upload_id,
            is_first_page=is_first_page,
            is_last_page=is_last_page,
            batch_index=batch_index,
            batch_count=batch_count,
            force_restart_upload=force_restart_upload,
            disable_stale_document_deletion_check=disable_stale_document_deletion_check,
        )

    with (
        patch.object(PushUploader, "index_documents", index_documents),
        patch.object(
            PushUploader,
            "bulk_index_single_batch_upload",
            bulk_index_single_batch_upload,
        ),
    ):
        yield captured


def wait_for_documents_to_index(
    datasource: str,
    documents: Sequence[DocumentDefinition],
    *,
    initial_wait_seconds: float,
    poll_interval_seconds: float,
    timeout_seconds: float,
) -> None:
    """Wait for uploaded documents to index, requesting immediate processing if needed."""
    debug_documents = _debug_document_requests(documents)
    if not debug_documents:
        return
    if initial_wait_seconds < 0 or timeout_seconds < 0 or poll_interval_seconds <= 0:
        raise ValueError("Indexing wait durations must be non-negative and poll interval positive")

    status_client = StatusClient(datasource=datasource)
    time.sleep(initial_wait_seconds)
    if _all_documents_indexed(status_client.get_documents_status(debug_documents), debug_documents):
        return

    try:
        PushUploader(datasource=datasource).process_all_documents()
    except ApiGleanError as error:
        if error.raw_response.status_code != 429:
            raise
        logger.warning(
            "Immediate document processing is rate-limited for datasource %r; continuing to poll",
            datasource,
        )

    poll_count = math.ceil(timeout_seconds / poll_interval_seconds)
    for _ in range(poll_count):
        time.sleep(poll_interval_seconds)
        if _all_documents_indexed(
            status_client.get_documents_status(debug_documents),
            debug_documents,
        ):
            return

    raise TimeoutError(
        f"{len(debug_documents)} document(s) for datasource {datasource!r} "
        f"did not finish indexing within {timeout_seconds:g} seconds"
    )


def _debug_document_requests(
    documents: Sequence[DocumentDefinition],
) -> list[DebugDocumentRequest]:
    requests: dict[tuple[str, str], DebugDocumentRequest] = {}
    for document in documents:
        if not document.id or not document.object_type:
            logger.warning(
                "Skipping indexing status check for a document without both id and object_type"
            )
            continue
        key = (document.object_type, document.id)
        requests[key] = DebugDocumentRequest(object_type=key[0], doc_id=key[1])
    return list(requests.values())


def _all_documents_indexed(
    response: DebugDocumentsResponse,
    expected_documents: Sequence[DebugDocumentRequest],
) -> bool:
    indexed: set[tuple[str, str]] = set()
    for item in response.document_statuses or []:
        status = item.debug_info.status if item.debug_info else None
        if item.object_type and item.doc_id and status and status.indexing_status == "INDEXED":
            indexed.add((item.object_type, item.doc_id))

    expected = {(document.object_type, document.doc_id) for document in expected_documents}
    return expected <= indexed
