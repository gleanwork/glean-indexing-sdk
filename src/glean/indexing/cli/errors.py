"""Error types for the `glean-idx` CLI.

Every failure the CLI raises deliberately carries three things: a stable
machine-readable ``code`` that agents can branch on, a human-readable message,
and — where one exists — a concrete ``hint`` naming the command that fixes it.
Exit codes are stable and documented so callers can react without parsing text.
"""

from __future__ import annotations

import sys
from typing import Any, Optional, Sequence

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
        detail: Optional[str] = None,
        hint: Optional[Sequence[str]] = None,
        searched: Optional[Sequence[str]] = None,
        docs: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
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
        """Render to stderr, as JSON when the run is in JSON mode."""
        # Imported here: output imports errors, so a module-level import would
        # be circular.
        from glean.indexing.cli.output import current_output_mode, render_error

        click.echo(render_error(self, current_output_mode()), file=file or sys.stderr)


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
