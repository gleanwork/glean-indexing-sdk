"""Error types for the `glean-idx` CLI.

Every failure the CLI raises deliberately carries three things: a stable
machine-readable ``code`` that agents can branch on, a human-readable message,
and — where one exists — a concrete ``hint`` naming the command that fixes it.
Exit codes are stable and documented so callers can react without parsing text.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Any

import click

EXIT_OK = 0
"""Command succeeded."""

EXIT_INTERNAL = 1
"""Unexpected failure inside the CLI or SDK."""

EXIT_USAGE = 2
"""Bad invocation. Click's own value for `UsageError`; do not reuse."""

EXIT_PRECONDITION = 3
"""The environment isn't ready: no credentials, no project, no connector."""

EXIT_REMOTE = 4
"""Glean rejected the request or was unreachable."""

EXIT_VALIDATION = 5
"""The command ran and found the subject invalid."""


class CliError(click.ClickException):
    """A CLI failure that renders identically in text and JSON output.

    Subclasses set ``code`` and ``exit_code``. `show` is what Click calls in
    standalone mode, so the rendering lives there rather than at each raise
    site.
    """

    code = "error"
    exit_code = EXIT_INTERNAL

    def __init__(
        self,
        message: str,
        *,
        detail: str | None = None,
        hint: Sequence[str] | None = None,
        searched: Sequence[str] | None = None,
        docs: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Build an error carrying its own remediation."""
        super().__init__(message)
        self.detail = detail
        self.hint = list(hint or [])
        self.searched = list(searched or [])
        self.docs = docs
        self.data = data or {}

    def as_dict(self) -> dict[str, Any]:
        """Machine-readable form, embedded in the JSON error envelope."""
        payload: dict[str, Any] = {"code": self.code, "message": self.format_message()}
        if self.detail:
            payload["detail"] = self.detail
        if self.hint:
            payload["hint"] = self.hint
        if self.searched:
            payload["searched"] = self.searched
        if self.docs:
            payload["docs"] = self.docs
        if self.data:
            payload["data"] = self.data
        return payload

    def show(self, file: Any = None) -> None:
        """Render the failure, to stdout in JSON mode and stderr otherwise.

        JSON mode is machine mode, and there stdout is the result channel: an
        `ok: false` envelope is still the result. Keeping it there means a caller
        parses one stream and never has to guess which. It matters most for
        `run`, whose connector logs share stderr — an envelope written there
        would arrive interleaved with them.

        Text mode keeps errors on stderr, where a person's tooling expects
        diagnostics to be.
        """
        # Imported here: output imports errors, so a module-level import would
        # be circular.
        from glean.indexing.cli.output import OutputMode, current_output_mode, render_error

        mode = current_output_mode()
        stream = file
        if stream is None:
            stream = sys.stdout if mode is OutputMode.JSON else sys.stderr
        click.echo(render_error(self, mode), file=stream)


class MissingCredentialsError(CliError):
    """`GLEAN_SERVER_URL` / `GLEAN_INDEXING_API_TOKEN` are not set."""

    code = "missing_credentials"
    exit_code = EXIT_PRECONDITION


class NoProjectError(CliError):
    """The command needs a connector project and none was found."""

    code = "no_project"
    exit_code = EXIT_PRECONDITION


class ConnectorNotImportableError(CliError):
    """The connector module or class could not be imported."""

    code = "connector_not_importable"
    exit_code = EXIT_PRECONDITION


class RemoteError(CliError):
    """Glean rejected the request, or could not be reached."""

    code = "remote_error"
    exit_code = EXIT_REMOTE


class ValidationFailedError(CliError):
    """The command ran successfully and found the subject invalid."""

    code = "validation_failed"
    exit_code = EXIT_VALIDATION


class ConfirmationRequiredError(CliError):
    """A mutating command needs explicit consent in non-interactive mode."""

    code = "confirmation_required"
    exit_code = EXIT_PRECONDITION


class DeploymentError(CliError):
    """A local or cloud deployment operation failed."""

    code = "deployment_error"


class ConnectorRunError(CliError):
    """The connector was loaded and started, and then raised.

    Distinct from `RemoteError`: the failure may be in the connector, the source
    system, or Glean, and the CLI cannot tell which. The traceback travels in
    `detail` because that is the only thing that makes a failed run debuggable.
    """

    code = "connector_run_failed"
    exit_code = EXIT_INTERNAL
