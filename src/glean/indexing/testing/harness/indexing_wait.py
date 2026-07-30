"""Document upload capture and indexing wait helpers for end-to-end tests."""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from unittest.mock import patch

from glean.api_client.errors import GleanError as ApiGleanError
from glean.api_client.models import DocumentDefinition
from glean.indexing.push import PushUploader
from glean.indexing.testing.indexing_status import (
    IndexingWaitResult,
    document_status_requests,
    poll_documents_status,
)

logger = logging.getLogger(__name__)

_INITIAL_INDEX_WAIT_SECONDS = 45


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
) -> IndexingWaitResult | None:
    """Wait for uploaded documents to index, requesting immediate processing if needed."""
    debug_documents = document_status_requests(documents)
    if not debug_documents:
        return None

    if any(not document.id or not document.object_type for document in documents):
        logger.warning("Skipping status checks for documents without both id and object_type")

    def process_all_documents() -> None:
        try:
            PushUploader(datasource=datasource).process_all_documents()
        except ApiGleanError as error:
            if error.raw_response.status_code != 429:
                raise
            logger.warning(
                "Immediate document processing is rate-limited for datasource %r; "
                "continuing to poll",
                datasource,
            )

    snapshot = poll_documents_status(
        datasource,
        debug_documents,
        initial_wait_seconds=_INITIAL_INDEX_WAIT_SECONDS,
        on_pending=process_all_documents,
    )
    if snapshot.result is IndexingWaitResult.INDEXED:
        return snapshot.result

    logger.warning(
        "Source data was pulled successfully, and Glean accepted the document upload without "
        "validation errors. The documents are queued for asynchronous indexing, which may take longer."
    )
    return IndexingWaitResult.PENDING
