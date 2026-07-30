"""Command-line document indexing status checks."""

from __future__ import annotations

import click
from glean.api_client.models import DebugDocumentRequest

from glean.indexing.testing.indexing_status import (
    IndexingStatusSnapshot,
    IndexingWaitResult,
    check_documents_status,
    poll_documents_status,
)


@click.command(name="glean-index-status")
@click.option("--datasource", required=True, help="Datasource name.")
@click.option(
    "--document",
    "documents",
    type=(str, str),
    multiple=True,
    required=True,
    metavar="OBJECT_TYPE DOCUMENT_ID",
    help="Document to check. Repeat for multiple documents.",
)
@click.option(
    "--poll",
    is_flag=True,
    help="Poll every 30 seconds for up to five minutes instead of checking once.",
)
def cli(datasource: str, documents: tuple[tuple[str, str], ...], poll: bool) -> None:
    """Check whether uploaded Glean documents have finished indexing."""
    requests = [
        DebugDocumentRequest(object_type=object_type, doc_id=document_id)
        for object_type, document_id in documents
    ]
    snapshot = (
        poll_documents_status(datasource, requests)
        if poll
        else check_documents_status(datasource, requests)
    )
    _print_snapshot(snapshot)


def _print_snapshot(snapshot: IndexingStatusSnapshot) -> None:
    click.echo(f"Result: {snapshot.result.value.upper()}")
    for item in snapshot.response.document_statuses or []:
        status = item.debug_info.status if item.debug_info else None
        click.echo(
            "  "
            f"{item.object_type or '<unknown>'}/{item.doc_id or '<unknown>'}: "
            f"upload={status.upload_status if status else 'STATUS_UNKNOWN'} "
            f"indexing={status.indexing_status if status else 'STATUS_UNKNOWN'} "
            f"permissions={status.permission_identity_status if status else 'STATUS_UNKNOWN'} "
            f"last_uploaded={status.last_uploaded_at if status else None} "
            f"last_indexed={status.last_indexed_at if status else None}"
        )

    if snapshot.result is IndexingWaitResult.PENDING:
        click.echo("Documents are still queued for asynchronous indexing.")


if __name__ == "__main__":
    cli()
