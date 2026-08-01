"""Per-invocation state shared by every `glean-idx` command."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from glean.indexing.cli.output import OutputMode


@dataclass
class CliContext:
    """Resolved invocation state, carried on Click's `ctx.obj`.

    Populated by the root group before any subcommand runs, so a command never
    has to re-derive global options or re-discover the project.
    """

    output: OutputMode
    assume_yes: bool = False
    project_override: Optional[Path] = None
    project_dir: Optional[Path] = None
    project_config: dict = field(default_factory=dict)
