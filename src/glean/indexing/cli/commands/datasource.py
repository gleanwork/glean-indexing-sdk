"""`glean-idx datasource` — the datasource as a whole, rather than one document.

`document` answers questions about a single record. The commands here act on the
container: what is in it, what shape it has, and how to empty it.
"""

from __future__ import annotations

from typing import Any, Optional

import click

from glean.indexing.cli.errors import RemoteError
from glean.indexing.cli.main import context, global_options
from glean.indexing.cli.output import emit
from glean.indexing.cli.preconditions import project_option, requires

DOCS = "https://developers.glean.com/libraries/indexing-sdk/status-and-debugging"

datasource_option = click.option("--datasource", required=True, help="Datasource name.")


def _remote(action: str, exc: Exception, datasource: str) -> RemoteError:
    """Wrap an API failure with the datasource it was attempted against."""
    return RemoteError(
        f"could not {action}",
        detail=str(exc),
        hint=[
            f"datasource: {datasource}",
            "glean-idx doctor --datasource <name>    check credentials",
        ],
        docs=DOCS,
    )


@click.group()
def datasource() -> None:
    """Inspect, configure, and empty a datasource."""


# --- status ---------------------------------------------------------------


@datasource.command("status")
@datasource_option
@global_options
@click.pass_context
@requires(credentials=True)
def datasource_status(
    ctx: click.Context,
    datasource: str,
    output: Optional[str],
    assume_yes: bool,
) -> None:
    """Summarize what Glean holds for a datasource.

    Document counts, identity counts, visibility, and the most recent upload and
    processing runs — the first thing to read when a crawl "worked" but nothing
    is searchable.
    """
    from glean.indexing.push import StatusClient

    cli_ctx = context(ctx, output=output, assume_yes=assume_yes)
    try:
        response = StatusClient(datasource=datasource).get_datasource_status()
    except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the operator
        raise _remote("read datasource status", exc, datasource) from exc

    data = _status_dict(datasource, response)
    emit(data, cli_ctx.output, text=_render_status(data))


def _counts(entries: Any) -> dict[str, int]:
    """`[{objectType, count}]` as a mapping, which is what callers want."""
    return {
        entry.object_type or "<unknown>": entry.count or 0
        for entry in (entries or [])
        if entry is not None
    }


def _latest(events: Any) -> Optional[dict[str, Any]]:
    """The most recent history event, by end time then start time.

    History arrives without a documented ordering, so it is sorted here rather
    than trusting the position of the last element.
    """
    ordered = sorted(
        (event for event in (events or []) if event is not None),
        key=lambda event: (
            getattr(event, "end_time", None) or "",
            getattr(event, "start_time", None) or "",
        ),
    )
    if not ordered:
        return None
    event = ordered[-1]
    latest = {
        "start_time": getattr(event, "start_time", None),
        "end_time": getattr(event, "end_time", None),
    }
    for field in ("upload_id", "status", "processing_state"):
        value = getattr(event, field, None)
        if value is not None:
            latest[field] = getattr(value, "value", value)
    return latest


def _identity_uploaded(component: Any) -> Optional[int]:
    """Uploaded count for one identity component, if reported."""
    counts = getattr(component, "counts", None)
    return getattr(counts, "uploaded", None)


def _status_dict(name: str, response: Any) -> dict[str, Any]:
    documents = getattr(response, "documents", None)
    identity = getattr(response, "identity", None)
    document_counts = getattr(documents, "counts", None)
    visibility = getattr(response, "datasource_visibility", None)

    return {
        "datasource": name,
        "visibility": getattr(visibility, "value", visibility),
        "documents": {
            # Uploaded is what the API accepted; indexed is what is searchable.
            # A gap between them is the whole reason to run this command.
            "uploaded": _counts(getattr(document_counts, "uploaded", None)),
            "indexed": _counts(getattr(document_counts, "indexed", None)),
            "last_bulk_upload": _latest(getattr(documents, "bulk_upload_history", None)),
            "last_processing": _latest(getattr(documents, "processing_history", None)),
        },
        "identity": {
            "users": _identity_uploaded(getattr(identity, "users", None)),
            "groups": _identity_uploaded(getattr(identity, "groups", None)),
            "memberships": _identity_uploaded(getattr(identity, "memberships", None)),
            "last_processing": _latest(getattr(identity, "processing_history", None)),
        },
    }


def _total(counts: dict[str, int]) -> int:
    return sum(counts.values())


def _render_counts(label: str, counts: dict[str, int]) -> list[str]:
    if not counts:
        return [f"    {label}: none reported"]
    by_type = ", ".join(f"{object_type}={count}" for object_type, count in sorted(counts.items()))
    return [f"    {label}: {_total(counts)} ({by_type})"]


def _render_event(label: str, event: Optional[dict[str, Any]]) -> list[str]:
    if not event:
        return []
    parts = [f"{key}={value}" for key, value in event.items() if value is not None]
    return [f"    {label}: {', '.join(parts)}"] if parts else []


def _render_status(data: dict[str, Any]) -> str:
    documents = data["documents"]
    identity = data["identity"]
    lines = [
        f"  Datasource: {data['datasource']}",
        f"  Visibility: {data['visibility'] or 'not reported'}",
        "  Documents:",
        *_render_counts("uploaded", documents["uploaded"]),
        *_render_counts("indexed", documents["indexed"]),
        *_render_event("last bulk upload", documents["last_bulk_upload"]),
        *_render_event("last processing", documents["last_processing"]),
    ]

    identity_counts = [
        f"{label}={identity[label]}"
        for label in ("users", "groups", "memberships")
        if identity[label] is not None
    ]
    lines.append("  Identity:")
    lines.append(f"    uploaded: {', '.join(identity_counts) or 'none reported'}")
    lines += _render_event("last processing", identity["last_processing"])

    uploaded, indexed = _total(documents["uploaded"]), _total(documents["indexed"])
    if uploaded and not indexed:
        lines.append("")
        lines.append("  Documents are uploaded but none are indexed yet.")
        lines.append("  Indexing is asynchronous; glean-idx datasource process requests a run.")
    return "\n".join(lines)


# --- configure ------------------------------------------------------------


@datasource.command("configure")
@click.option(
    "--connector",
    "reference",
    default=None,
    metavar="MODULE:CLASS",
    help="Connector to read the configuration from. Defaults to the project file's connector.",
)
@click.option(
    "--show",
    is_flag=True,
    help="Print the configuration that would be registered, without calling Glean.",
)
@project_option
@global_options
@click.pass_context
@requires(credentials=True, project=True)
def datasource_configure(
    ctx: click.Context,
    reference: Optional[str],
    show: bool,
    project_dir: Optional[Any],
    output: Optional[str],
    assume_yes: bool,
) -> None:
    """Register the connector's datasource configuration with Glean.

    The configuration is read from the connector class rather than passed in, so
    the datasource Glean knows about cannot drift from the one the connector
    uploads to. This is the first step of any new connector: object definitions
    have to exist before documents referencing them will index.
    """
    from glean.indexing.cli.project import load_connector
    from glean.indexing.push import PushUploader

    cli_ctx = context(ctx, output=output, assume_yes=assume_yes, project_dir=project_dir)
    assert cli_ctx.project_dir is not None  # guaranteed by requires(project=True)

    connector_class = load_connector(cli_ctx.project_dir, cli_ctx.project_config, reference)
    config = _connector_configuration(connector_class)

    data: dict[str, Any] = {
        "datasource": config.name,
        "configuration": _configuration_dict(config),
        "registered": False,
    }
    if show:
        emit(data, cli_ctx.output, text=_render_configuration(data, registered=False))
        return

    try:
        PushUploader(datasource=config.name).configure_datasource(config)
    except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the operator
        raise _remote("register the datasource configuration", exc, config.name) from exc

    data["registered"] = True
    emit(data, cli_ctx.output, text=_render_configuration(data, registered=True))


def _connector_configuration(connector_class: Any) -> Any:
    """The connector's `configuration`, whether declared on the class or built in `__init__`."""
    from glean.indexing.cli.errors import ConnectorNotImportableError

    config = getattr(connector_class, "configuration", None)
    if config is None:
        try:
            config = getattr(connector_class(), "configuration", None)
        except Exception as exc:  # noqa: BLE001 - the connector's own constructor failed
            raise ConnectorNotImportableError(
                f"could not read a configuration from {connector_class.__name__}",
                detail=str(exc),
                hint=[
                    "declare configuration as a class attribute, or make the constructor "
                    "callable with no arguments",
                ],
                docs=DOCS,
            ) from exc

    if config is None or not hasattr(config, "name"):
        raise ConnectorNotImportableError(
            f"{connector_class.__name__} does not define a datasource configuration",
            detail="Expected a CustomDatasourceConfig on the connector's `configuration`.",
            hint=["configuration = CustomDatasourceConfig(name=..., display_name=...)"],
            docs=DOCS,
        )
    return config


def _configuration_dict(value: Any) -> Any:
    """A configuration as plain JSON-safe data, keyed by field name.

    `model_dump()` is not used here: on some pydantic and api-client version
    pairs it returns camelCase keys even with `by_alias=False`, and it fills in
    defaults for fields the connector never set. Walking `model_fields_set`
    keeps the keys snake_case like the rest of this CLI's output, and keeps the
    payload to what the connector actually declared. `configure_datasource`
    builds its request the same way, for the same reason.
    """
    fields = getattr(type(value), "model_fields", None)
    if fields is not None and hasattr(value, "model_fields_set"):
        return {
            name: _configuration_dict(getattr(value, name))
            for name in fields
            if name in value.model_fields_set
        }
    if isinstance(value, (list, tuple)):
        return [_configuration_dict(item) for item in value]
    return getattr(value, "value", value)


def _render_configuration(data: dict[str, Any], *, registered: bool) -> str:
    config = data["configuration"]
    object_types = [
        definition.get("name", "<unnamed>")
        for definition in (config.get("object_definitions") or [])
    ]
    lines = [
        f"  Datasource: {data['datasource']}",
        f"  Display name: {config.get('display_name') or 'not set'}",
        f"  Category: {config.get('datasource_category') or 'not set'}",
        f"  Object types: {', '.join(object_types) or 'none defined'}",
        "",
        "  Registered." if registered else "  Not registered (--show).",
    ]
    return "\n".join(lines)


# --- process --------------------------------------------------------------


@datasource.command("process")
@datasource_option
@global_options
@click.pass_context
@requires(credentials=True)
def datasource_process(
    ctx: click.Context,
    datasource: str,
    output: Optional[str],
    assume_yes: bool,
) -> None:
    """Request processing of all uploaded documents.

    Glean processes uploads on its own schedule. This asks for a run now, which
    is what turns an upload into a searchable document during development.
    Returns as soon as the request is accepted, not when processing finishes.
    """
    from glean.indexing.push import PushUploader

    cli_ctx = context(ctx, output=output, assume_yes=assume_yes)
    try:
        PushUploader(datasource=datasource).process_all_documents()
    except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the operator
        raise _remote("request document processing", exc, datasource) from exc

    emit(
        {"datasource": datasource, "requested": True},
        cli_ctx.output,
        text=(
            f"  Requested processing for {datasource}.\n"
            "  Processing runs asynchronously; check glean-idx datasource status."
        ),
    )


# --- teardown -------------------------------------------------------------


@datasource.command("teardown")
@datasource_option
@global_options
@click.pass_context
@requires(credentials=True)
def datasource_teardown(
    ctx: click.Context,
    datasource: str,
    output: Optional[str],
    assume_yes: bool,
) -> None:
    """Delete every document in a datasource.

    Uploads a single empty page as a complete bulk upload, so every document
    already in the datasource becomes stale and is removed. The datasource
    itself and its configuration survive, which is what makes this useful
    between test runs.
    """
    from glean.indexing.push import PushUploader

    cli_ctx = context(ctx, output=output, assume_yes=assume_yes)

    # Unrecoverable and unscoped, so a y/N keypress is too easy to give by
    # accident. Naming the datasource is the same bar `terraform destroy` sets.
    if not cli_ctx.assume_yes:
        click.echo(f"This deletes every document in {datasource!r}. It cannot be undone.")
        if click.prompt("Type the datasource name to confirm", default="", show_default=False) != (
            datasource
        ):
            raise click.Abort()

    try:
        # One empty page, marked both first and last: a complete upload
        # containing nothing, with the stale-deletion guard lifted.
        PushUploader(datasource=datasource).bulk_index_document_batches(
            [[]],
            batch_count=1,
            force_restart_upload=True,
            disable_stale_document_deletion_check=True,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the operator
        raise _remote("empty the datasource", exc, datasource) from exc

    emit(
        {"datasource": datasource, "emptied": True},
        cli_ctx.output,
        text=(f"  Emptied {datasource}.\n  The datasource and its configuration are unchanged."),
    )
