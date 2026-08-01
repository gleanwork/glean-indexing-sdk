"""`glean-idx doctor` — check that the environment is ready before anything else.

A bad or missing token otherwise surfaces part-way through a crawl, as a
`MissingEnvironmentVariableError` from whichever call happened to run first.
This turns that into one deliberate, early check with an actionable result.
"""

from __future__ import annotations

import os
import sys
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Optional

import click

from glean.indexing.cli.errors import MissingCredentialsError, RemoteError
from glean.indexing.cli.main import context, global_options
from glean.indexing.cli.output import emit

SERVER_URL_VAR = "GLEAN_SERVER_URL"
LEGACY_INSTANCE_VAR = "GLEAN_INSTANCE"
TOKEN_VAR = "GLEAN_INDEXING_API_TOKEN"

DOCS = "https://developers.glean.com/libraries/indexing-sdk/quickstart"


def _sdk_version() -> str:
    try:
        return version("glean-indexing-sdk")
    except PackageNotFoundError:  # pragma: no cover - only when running from source
        return "unknown"


def _isolated_run() -> bool:
    """Whether this looks like an ephemeral `uvx` environment.

    Used only to add context to a message. `uv` leaves no dedicated marker, so
    this keys off the cache-backed prefix it runs from; a false negative just
    means one fewer hint.
    """
    return "/uv/" in sys.prefix.replace(os.sep, "/")


def _check_env() -> tuple[list[dict[str, Any]], list[str]]:
    """Presence checks for the two variables every command needs."""
    server_url = os.getenv(SERVER_URL_VAR)
    instance = os.getenv(LEGACY_INSTANCE_VAR)
    token = os.getenv(TOKEN_VAR)

    checks: list[dict[str, Any]] = []
    missing: list[str] = []

    if server_url:
        checks.append({"name": SERVER_URL_VAR, "ok": True, "value": server_url})
    elif instance:
        checks.append(
            {
                "name": SERVER_URL_VAR,
                "ok": True,
                "value": f"{LEGACY_INSTANCE_VAR}={instance}",
                "note": f"{LEGACY_INSTANCE_VAR} is deprecated; prefer {SERVER_URL_VAR}.",
            }
        )
    else:
        checks.append({"name": SERVER_URL_VAR, "ok": False})
        missing.append(SERVER_URL_VAR)

    # Never echo the token: presence and length are enough to diagnose with.
    if token:
        checks.append({"name": TOKEN_VAR, "ok": True, "value": f"set ({len(token)} chars)"})
    else:
        checks.append({"name": TOKEN_VAR, "ok": False})
        missing.append(TOKEN_VAR)

    return checks, missing


def _probe(datasource: str) -> dict[str, Any]:
    """Prove the token actually works by reading a datasource's status."""
    from glean.indexing.push import StatusClient

    try:
        StatusClient(datasource=datasource).get_datasource_status()
    except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the operator
        raise RemoteError(
            f"could not read status for datasource {datasource!r}",
            detail=str(exc),
            hint=[
                "confirm the datasource name is correct",
                f"confirm the {TOKEN_VAR} is scoped to that datasource",
            ],
            docs=DOCS,
        ) from exc
    return {"name": f"datasource:{datasource}", "ok": True, "value": "reachable"}


def _render(checks: list[dict[str, Any]], missing: list[str]) -> str:
    lines = []
    for check in checks:
        mark = "OK  " if check["ok"] else "MISS"
        value = check.get("value", "not set")
        lines.append(f"  [{mark}] {check['name']}: {value}")
        if check.get("note"):
            lines.append(f"         {check['note']}")
    if not missing:
        # Remediation for the failing case belongs to the error block, which
        # already renders hints and docs; repeating it here would duplicate.
        lines += ["", "  Ready."]
    return "\n".join(lines)


def _plural(items: list[str]) -> str:
    return "variable" if len(items) == 1 else "variables"


@click.command()
@click.option(
    "--datasource",
    default=None,
    help="Also read this datasource's status, proving the token works.",
)
@global_options
@click.pass_context
def doctor(
    ctx: click.Context,
    datasource: Optional[str],
    output: Optional[str],
    assume_yes: bool,
) -> None:
    """Check credentials and, optionally, reach Glean."""
    cli_ctx = context(ctx, output=output, assume_yes=assume_yes)
    checks, missing = _check_env()

    if not missing and datasource:
        checks.append(_probe(datasource))

    data: dict[str, Any] = {
        "ready": not missing,
        "sdk_version": _sdk_version(),
        "isolated_run": _isolated_run(),
        "checks": checks,
    }

    # `ok` has to mean "achieved its purpose" for every command, or agents
    # cannot branch on it. Doctor's purpose is a ready environment, so an
    # unready one is a failure — carrying the checks along so nothing measured
    # is lost.
    if missing:
        raise MissingCredentialsError(
            f"missing required environment {_plural(missing)}: {', '.join(missing)}",
            detail=_render(checks, missing),
            hint=[f"export {name}=..." for name in missing],
            docs=DOCS,
            data=data,
        )

    emit(data, cli_ctx.output, text=_render(checks, missing))
