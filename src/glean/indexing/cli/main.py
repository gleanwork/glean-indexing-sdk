"""Root group for `glean-idx`.

Commands are loaded lazily. `glean-idx document status` should not pay to import
Jinja2 and the cloud SDKs that `deploy` needs, and a CLI invoked repeatedly by an
agent notices the difference.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Optional

import click

from glean.indexing.cli.context import CliContext
from glean.indexing.cli.output import OutputMode, resolve_output_mode, set_output_mode

CONTEXT_SETTINGS = {
    "help_option_names": ["-h", "--help"],
    "max_content_width": 100,
}

#: Subcommand name -> "module:attribute", imported on first use.
COMMANDS: dict[str, str] = {
    "datasource": "glean.indexing.cli.commands.datasource:datasource",
    "deploy": "glean.indexing.cli.commands.deploy:deploy",
    "doctor": "glean.indexing.cli.commands.doctor:doctor",
    "document": "glean.indexing.cli.commands.document:document",
    "validate": "glean.indexing.cli.commands.validate:validate",
}

# Click rewraps help text paragraph by paragraph, which folds the example
# commands onto adjacent lines and breaks them mid-token. A `\b` line marks the
# paragraph after it as preformatted, so these stay copy-pasteable.
EPILOG = """\
Where to run these:

\b
  Most commands need only credentials, and run anywhere:
    uvx --from glean-indexing-sdk glean-idx doctor

\b
  Commands that load your connector (run, test, datasource configure) must run
  inside your connector project, with the SDK installed alongside your code:
    uv run glean-idx run

\b
Docs: https://developers.glean.com/libraries/indexing-sdk
"""


class LazyGroup(click.Group):
    """A group whose subcommands are imported on demand."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        """Every known command, whether or not it has been imported."""
        return sorted(set(super().list_commands(ctx)) | set(COMMANDS))

    def get_command(self, ctx: click.Context, cmd_name: str) -> Optional[click.Command]:
        """Import and return a command the first time it is used."""
        registered = super().get_command(ctx, cmd_name)
        if registered is not None:
            return registered
        target = COMMANDS.get(cmd_name)
        if target is None:
            return None
        module_name, _, attr = target.partition(":")
        return getattr(importlib.import_module(module_name), attr)


@click.group(cls=LazyGroup, context_settings=CONTEXT_SETTINGS, epilog=EPILOG)
@click.version_option(package_name="glean-indexing-sdk", prog_name="glean-idx")
@click.option(
    "--output",
    "output",
    type=click.Choice([mode.value for mode in OutputMode]),
    default=None,
    help="Output format. Defaults to text at a terminal, json when redirected.",
)
@click.option(
    "--yes",
    "-y",
    "assume_yes",
    is_flag=True,
    default=False,
    help="Assume yes for every confirmation. Required for unattended use.",
)
@click.pass_context
def cli(ctx: click.Context, output: Optional[str], assume_yes: bool) -> None:
    """Build, test, and operate Glean custom connectors."""
    resolved = resolve_output_mode(output)
    set_output_mode(resolved)
    ctx.obj = CliContext(output=resolved, assume_yes=assume_yes)


def context(
    ctx: click.Context,
    *,
    output: Optional[str] = None,
    assume_yes: bool = False,
    project_dir: Optional[Path] = None,
) -> CliContext:
    """The resolved `CliContext`, applying any command-level overrides.

    Commands invoked directly in tests may not have gone through the root
    group, so a default is created rather than requiring special-casing.
    """
    existing: Any = ctx.find_object(CliContext)
    if existing is None:
        existing = CliContext(output=resolve_output_mode(None))
        ctx.obj = existing
    if output:
        existing.output = OutputMode(output)
    if assume_yes:
        existing.assume_yes = True
    if project_dir is not None:
        existing.project_override = project_dir
    set_output_mode(existing.output)
    return existing


def global_options(func: Any) -> Any:
    """Re-expose the root group's global flags on a subcommand.

    Click only parses group options before the subcommand name. Attaching them
    here too means `glean-idx doctor --output json` works as well as
    `glean-idx --output json doctor`.
    """
    func = click.option(
        "--yes",
        "-y",
        "assume_yes",
        is_flag=True,
        default=False,
        help="Assume yes for every confirmation. Required for unattended use.",
    )(func)
    return click.option(
        "--output",
        "output",
        type=click.Choice([mode.value for mode in OutputMode]),
        default=None,
        help="Output format. Defaults to text at a terminal, json when redirected.",
    )(func)
