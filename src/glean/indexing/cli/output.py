"""Output rendering for the `glean-idx` CLI.

Two modes, one envelope. Text is for people; JSON is for agents and pipelines.
The default is chosen by whether stdout is a terminal, so a skill that pipes
output gets JSON without having to pass a flag, and a person at a prompt gets
readable text without having to know one exists. `--output` overrides both ways.
"""

from __future__ import annotations

import json
import sys
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

import click

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from glean.indexing.cli.errors import CliError


class OutputMode(str, Enum):
    """How a command renders its result."""

    TEXT = "text"
    JSON = "json"


def default_output_mode() -> OutputMode:
    """Text at a terminal, JSON when redirected."""
    return OutputMode.TEXT if sys.stdout.isatty() else OutputMode.JSON


def resolve_output_mode(explicit: Optional[str]) -> OutputMode:
    """Honour an explicit `--output`, else infer from the stream."""
    return OutputMode(explicit) if explicit else default_output_mode()


#: The mode resolved for this process, recorded so error rendering can find it.
#: Click catches `ClickException` outside the command's context, so by the time
#: `CliError.show` runs there is no current context to read `--output` back off.
_resolved_mode: Optional[OutputMode] = None


def set_output_mode(mode: Optional[OutputMode]) -> None:
    """Record the resolved mode for the rest of this invocation."""
    global _resolved_mode
    _resolved_mode = mode


def current_output_mode() -> OutputMode:
    """The mode for the running command.

    Prefers the recorded resolution, then any live Click context, then stream
    detection — so an error raised while parsing global flags still renders.
    """
    if _resolved_mode is not None:
        return _resolved_mode
    ctx = click.get_current_context(silent=True)
    obj = getattr(ctx, "obj", None) if ctx is not None else None
    mode = getattr(obj, "output", None)
    return mode if isinstance(mode, OutputMode) else default_output_mode()


def render_error(error: "CliError", mode: OutputMode) -> str:
    """Format a failure for the given mode."""
    if mode is OutputMode.JSON:
        return json.dumps({"ok": False, "error": error.as_dict()}, indent=2)

    lines = [f"Error: {error.format_message()}  [{error.code}]"]
    if error.detail:
        lines += ["", *_indent(error.detail.splitlines())]
    if error.searched:
        lines += ["", "  Searched:", *[f"    {path}" for path in error.searched]]
    if error.hint:
        # Not "do one of": some errors list steps that are all required (both
        # missing environment variables), others list alternatives (a connector
        # reference, or a different directory). "Hint" is true either way.
        lines += ["", f"  {'Hint' if len(error.hint) == 1 else 'Hints'}:"]
        lines += [f"    {item}" for item in error.hint]
    if error.docs:
        lines += ["", f"  {error.docs}"]
    return "\n".join(lines)


def emit(data: Any, mode: OutputMode, *, text: Optional[str] = None) -> None:
    """Write a successful result to stdout.

    `text` is the human rendering; when absent, JSON is used for both so a
    command is never silently unreadable.
    """
    if mode is OutputMode.JSON:
        click.echo(json.dumps({"ok": True, "data": data}, indent=2, default=str))
    else:
        click.echo(text if text is not None else json.dumps(data, indent=2, default=str))


def _indent(lines: list[str]) -> list[str]:
    return [f"  {line}" if line else "" for line in lines]
