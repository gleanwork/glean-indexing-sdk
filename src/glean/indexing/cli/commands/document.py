"""`glean-idx document` — inspect and remove individual indexed documents.

The commands here answer the question that follows every crawl: did *this*
document land, and can the right people see it. Each needs only credentials, so
they run anywhere — including `uvx`, before you have a project.
"""

from __future__ import annotations

from typing import Any, Optional

import click

from glean.indexing.cli.errors import RemoteError
from glean.indexing.cli.main import context, global_options
from glean.indexing.cli.output import emit
from glean.indexing.cli.preconditions import requires

DOCS = "https://developers.glean.com/libraries/indexing-sdk/status-and-debugging"

#: `--document OBJECT_TYPE DOCUMENT_ID`, repeatable. Two values rather than one
#: because the indexing API keys documents on the pair, not the id alone.
document_argument = click.option(
    "--document",
    "documents",
    type=(str, str),
    multiple=True,
    required=True,
    metavar="OBJECT_TYPE DOCUMENT_ID",
    help="Document to act on. Repeat for several.",
)

datasource_option = click.option("--datasource", required=True, help="Datasource name.")


def _remote(action: str, exc: Exception, **hint_context: str) -> RemoteError:
    """Wrap an API failure with the datasource it was attempted against."""
    hints = [f"{key}: {value}" for key, value in hint_context.items()]
    return RemoteError(
        f"could not {action}",
        detail=str(exc),
        hint=[*hints, "glean-idx doctor --datasource <name>    check credentials"],
        docs=DOCS,
    )


@click.group()
def document() -> None:
    """Inspect and remove indexed documents."""


@document.command("status")
@datasource_option
@document_argument
@click.option(
    "--poll",
    is_flag=True,
    help="Poll every 30 seconds for up to five minutes instead of checking once.",
)
@global_options
@click.pass_context
@requires(credentials=True)
def document_status(
    ctx: click.Context,
    datasource: str,
    documents: tuple[tuple[str, str], ...],
    poll: bool,
    output: Optional[str],
    assume_yes: bool,
) -> None:
    """Check whether documents have finished indexing.

    Indexing is asynchronous, so an accepted upload is not yet a searchable
    document. `--poll` waits for the transition rather than sampling once.
    """
    from glean.api_client.models import DebugDocumentRequest

    from glean.indexing.push.status import check_documents_status, poll_documents_status

    cli_ctx = context(ctx, output=output, assume_yes=assume_yes)
    requests = [
        DebugDocumentRequest(object_type=object_type, doc_id=document_id)
        for object_type, document_id in documents
    ]

    try:
        snapshot = (
            poll_documents_status(datasource, requests)
            if poll
            else check_documents_status(datasource, requests)
        )
    except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the operator
        raise _remote("read document status", exc, datasource=datasource) from exc

    data = {
        "datasource": datasource,
        "result": snapshot.result.value,
        "documents": [_status_dict(item) for item in (snapshot.response.document_statuses or [])],
    }
    emit(data, cli_ctx.output, text=_render_status(data))


def _status_dict(item: Any) -> dict[str, Any]:
    """Flatten one response item.

    `object_type` and `doc_id` sit on the item itself; the status fields sit
    under `debug_info.status`, and either level can be absent.
    """
    status = item.debug_info.status if item.debug_info else None
    return {
        "object_type": item.object_type,
        "document_id": item.doc_id,
        "upload_status": getattr(status, "upload_status", None),
        "indexing_status": getattr(status, "indexing_status", None),
        "permission_identity_status": getattr(status, "permission_identity_status", None),
        "last_uploaded_at": getattr(status, "last_uploaded_at", None),
        "last_indexed_at": getattr(status, "last_indexed_at", None),
    }


UNKNOWN = "STATUS_UNKNOWN"


def _render_status(data: dict[str, Any]) -> str:
    lines = [f"  Result: {data['result'].upper()}"]
    for item in data["documents"]:
        lines.append(
            f"    {item['object_type'] or '<unknown>'}/{item['document_id'] or '<unknown>'}: "
            f"upload={item['upload_status'] or UNKNOWN} "
            f"indexing={item['indexing_status'] or UNKNOWN} "
            f"permissions={item['permission_identity_status'] or UNKNOWN} "
            f"last_uploaded={item['last_uploaded_at']} "
            f"last_indexed={item['last_indexed_at']}"
        )
    if data["result"] == "pending":
        lines.append("  Documents are still queued for asynchronous indexing.")
    return "\n".join(lines)


@document.command("access")
@datasource_option
@click.option("--object-type", required=True, help="Document object type.")
@click.option("--id", "document_id", required=True, help="Document ID.")
@click.option("--user", "user_email", required=True, help="Email of the user to check.")
@global_options
@click.pass_context
@requires(credentials=True)
def document_access(
    ctx: click.Context,
    datasource: str,
    object_type: str,
    document_id: str,
    user_email: str,
    output: Optional[str],
    assume_yes: bool,
) -> None:
    """Check whether a user can see a document.

    The highest-value permissions check there is: an upload that succeeded with a
    correct-looking ACL is still wrong if the identity graph is incomplete, and
    only a real access check catches that.
    """
    from glean.indexing.push import StatusClient

    cli_ctx = context(ctx, output=output, assume_yes=assume_yes)
    try:
        response = StatusClient(datasource=datasource).check_document_access(
            object_type=object_type, document_id=document_id, user_email=user_email
        )
    except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the operator
        raise _remote(
            "check document access", exc, datasource=datasource, document=document_id
        ) from exc

    allowed = getattr(response, "has_access", None)
    data = {
        "datasource": datasource,
        "object_type": object_type,
        "document_id": document_id,
        "user": user_email,
        "has_access": allowed,
    }
    verdict = "can" if allowed else "cannot"
    emit(data, cli_ctx.output, text=f"  {user_email} {verdict} access {object_type}/{document_id}")


@document.command("delete")
@datasource_option
@document_argument
@global_options
@click.pass_context
@requires(credentials=True)
def document_delete(
    ctx: click.Context,
    datasource: str,
    documents: tuple[tuple[str, str], ...],
    output: Optional[str],
    assume_yes: bool,
) -> None:
    """Delete documents from the index."""
    from glean.indexing.push import PushUploader

    cli_ctx = context(ctx, output=output, assume_yes=assume_yes)
    if not cli_ctx.assume_yes:
        click.confirm(
            f"Permanently delete {len(documents)} document(s) from {datasource!r}?", abort=True
        )

    uploader = PushUploader(datasource=datasource)
    deleted = []
    for object_type, document_id in documents:
        try:
            uploader.delete_document(object_type=object_type, document_id=document_id)
        except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the operator
            raise _remote(
                f"delete {object_type}/{document_id}", exc, datasource=datasource
            ) from exc
        deleted.append({"object_type": object_type, "document_id": document_id})

    data = {"datasource": datasource, "deleted": deleted}
    emit(data, cli_ctx.output, text=f"  Deleted {len(deleted)} document(s) from {datasource}.")


@document.command("events")
@datasource_option
@click.option("--object-type", required=True, help="Document object type.")
@click.option("--id", "document_id", required=True, help="Document ID.")
@click.option("--start-date", default=None, help="Only events on or after this date.")
@click.option("--max-events", type=int, default=None, help="Cap the number of events returned.")
@global_options
@click.pass_context
@requires(credentials=True)
def document_events(
    ctx: click.Context,
    datasource: str,
    object_type: str,
    document_id: str,
    start_date: Optional[str],
    max_events: Optional[int],
    output: Optional[str],
    assume_yes: bool,
) -> None:
    """Show a document's lifecycle events.

    Answers "where did my document go?" when it uploaded successfully but never
    became searchable.
    """
    from glean.indexing.push import PushUploader

    cli_ctx = context(ctx, output=output, assume_yes=assume_yes)
    try:
        response = PushUploader(datasource=datasource).get_document_lifecycle_events(
            object_type=object_type,
            document_id=document_id,
            start_date=start_date,
            max_events=max_events,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the operator
        raise _remote(
            "read lifecycle events", exc, datasource=datasource, document=document_id
        ) from exc

    events = getattr(response, "events", None) or []
    data = {
        "datasource": datasource,
        "object_type": object_type,
        "document_id": document_id,
        "events": [_event_dict(event) for event in events],
    }
    text = "\n".join(f"  {line}" for line in (_render_events(data["events"]) or ["No events."]))
    emit(data, cli_ctx.output, text=text)


def _event_dict(event: Any) -> dict[str, Any]:
    """Best-effort flattening; the event model varies by event type."""
    if hasattr(event, "model_dump"):
        return event.model_dump(exclude_none=True)
    return {"event": str(event)}


def _render_events(events: list[dict[str, Any]]) -> list[str]:
    return [", ".join(f"{key}={value}" for key, value in event.items()) for event in events]
