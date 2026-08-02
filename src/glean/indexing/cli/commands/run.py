"""`glean-idx run` — execute a connector against Glean.

The command the whole CLI exists to support. Everything else either prepares for
this or inspects what it produced.

Deliberately matched to how the deployed connector runs: the generated Kubernetes
entrypoint imports the class named in the project file, constructs it with no
arguments, and calls `index_data(mode=...)`. Running the connector locally
through a different path would mean local success proving nothing about
production.
"""

from __future__ import annotations

import logging
import sys
import time
import traceback
from pathlib import Path
from typing import Optional

import click

from glean.indexing.cli.errors import ConnectorRunError
from glean.indexing.cli.main import context, global_options
from glean.indexing.cli.output import OutputMode, emit
from glean.indexing.cli.preconditions import project_option, requires

DOCS = "https://developers.glean.com/libraries/indexing-sdk/running-connectors"

LOG_LEVELS = ("debug", "info", "warning", "error")


class _StderrLoggerProvider:
    """Sends connector logs to stderr.

    In JSON mode stdout carries exactly one envelope, and the connector's own
    logging would otherwise interleave with it and make the output unparseable.
    `setup_connector_logging` always attaches a stdout handler unless it is given
    a provider, so this uses that seam rather than reconfiguring the logger here.
    """

    def setup_handler(self, logger_name: str, level: int = logging.INFO) -> logging.Handler:
        """A stderr handler at the requested level."""
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        return handler

    def flush(self) -> None:
        """Nothing is buffered."""


@click.command()
@click.option(
    "--connector",
    "reference",
    default=None,
    metavar="MODULE:CLASS",
    help="Connector to run. Defaults to the project file's connector.",
)
@click.option(
    "--mode",
    type=click.Choice(["full", "incremental"]),
    default=None,
    help="Indexing mode. Defaults to the project file's indexing_mode, or full.",
)
@click.option("--force-restart", is_flag=True, help="Discard any partial upload and start over.")
@click.option(
    "--disable-stale-deletion-check",
    is_flag=True,
    help="Delete stale documents synchronously once the upload completes.",
)
@click.option("--upload-timeout-ms", type=int, default=None, help="Per-request upload timeout.")
@click.option(
    "--batch-size-bytes",
    type=int,
    default=None,
    help="Maximum serialized bytes per upload batch.",
)
@click.option("--max-workers", type=int, default=None, help="Concurrent middle-page uploads.")
@click.option(
    "--log-level",
    type=click.Choice(LOG_LEVELS, case_sensitive=False),
    default="info",
    show_default=True,
    help="Connector log level. Logs go to stderr.",
)
@project_option
@global_options
@click.pass_context
@requires(credentials=True, project=True)
def run(
    ctx: click.Context,
    reference: Optional[str],
    mode: Optional[str],
    force_restart: bool,
    disable_stale_deletion_check: bool,
    upload_timeout_ms: Optional[int],
    batch_size_bytes: Optional[int],
    max_workers: Optional[int],
    log_level: str,
    project_dir: Optional[Path],
    output: Optional[str],
    assume_yes: bool,
) -> None:
    """Run a connector: fetch from the source, transform, and upload to Glean.

    A full crawl is a complete replacement of the indexed state, so documents
    Glean holds that this run does not produce are treated as stale and removed.
    Point `--mode incremental` at a connector that supports it to avoid that.
    """
    from glean.indexing.models import ConnectorOptions, IndexingMode
    from glean.indexing.observability import setup_connector_logging

    from glean.indexing.cli.project import instantiate_connector, load_connector

    cli_ctx = context(ctx, output=output, assume_yes=assume_yes, project_dir=project_dir)
    assert cli_ctx.project_dir is not None  # guaranteed by requires(project=True)

    resolved_mode = IndexingMode(mode or cli_ctx.project_config.get("indexing_mode") or "full")
    connector_class = load_connector(cli_ctx.project_dir, cli_ctx.project_config, reference)
    connector = instantiate_connector(connector_class)

    options = ConnectorOptions(
        force_restart=force_restart,
        disable_stale_deletion_check=disable_stale_deletion_check,
        **({"upload_timeout_ms": upload_timeout_ms} if upload_timeout_ms is not None else {}),
        **({"document_batch_size_bytes": batch_size_bytes} if batch_size_bytes is not None else {}),
        **({"upload_max_workers": max_workers} if max_workers is not None else {}),
    )

    name = getattr(connector, "name", None) or connector_class.__name__
    setup_connector_logging(
        connector_name=name,
        log_level=log_level.upper(),
        use_structured_logging=cli_ctx.output is OutputMode.JSON,
        logger_provider=_StderrLoggerProvider(),  # type: ignore[arg-type]
    )

    started = time.monotonic()
    try:
        connector.index_data(mode=resolved_mode, options=options)
    except Exception as exc:  # noqa: BLE001 - reported with its traceback
        raise ConnectorRunError(
            f"{connector_class.__name__} failed after {_elapsed(started)}",
            detail=traceback.format_exc().rstrip(),
            hint=[
                "glean-idx doctor --datasource <name>    check credentials and reachability",
                f"glean-idx datasource status --datasource {name}    see what was uploaded",
            ],
            docs=DOCS,
            data={
                "connector": connector_class.__name__,
                "datasource": name,
                "mode": resolved_mode.value,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        ) from exc

    data = {
        "connector": connector_class.__name__,
        "datasource": name,
        "mode": resolved_mode.value,
        "duration_seconds": round(time.monotonic() - started, 3),
    }
    emit(
        data,
        cli_ctx.output,
        text=(
            f"  Ran {connector_class.__name__} against {name} "
            f"({resolved_mode.value}) in {_elapsed(started)}.\n"
            f"  Indexing is asynchronous; "
            f"glean-idx datasource status --datasource {name} shows progress."
        ),
    )


def _elapsed(started: float) -> str:
    return f"{time.monotonic() - started:.1f}s"
