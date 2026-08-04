"""`glean-idx completion` — shell completion for interactive use.

Click can complete commands and options, but only once the shell has been told
how. The documented way is an incantation involving an internal environment
variable; printing the script from a real subcommand is something a person can
discover from `--help`.
"""

from __future__ import annotations

from typing import Optional

import click
from click.shell_completion import get_completion_class

from glean.indexing.cli.errors import EXIT_USAGE, CliError
from glean.indexing.cli.main import context, global_options

DOCS = "https://developers.glean.com/libraries/indexing-sdk/cli"

#: The variable Click derives from the executable name, spelled out because the
#: emitted script has to match what the installed `glean-idx` looks for.
COMPLETE_VAR = "_GLEAN_IDX_COMPLETE"

SHELLS = ("bash", "zsh", "fish")

INSTALL_HINTS = {
    "bash": "glean-idx completion bash >> ~/.bashrc",
    "zsh": "glean-idx completion zsh >> ~/.zshrc",
    "fish": "glean-idx completion fish > ~/.config/fish/completions/glean-idx.fish",
}


class UnsupportedShellError(CliError):
    """Click has no completion implementation for the requested shell."""

    code = "unsupported_shell"
    exit_code = EXIT_USAGE


@click.command()
@click.argument("shell", type=click.Choice(SHELLS))
@global_options
@click.pass_context
def completion(
    ctx: click.Context,
    shell: str,
    output: Optional[str],
    assume_yes: bool,
) -> None:
    """Print the shell completion script for SHELL.

    Add it to your shell's startup file, for example:

    \b
      glean-idx completion zsh >> ~/.zshrc
    """
    # Resolved so that --output is accepted and honoured for failures; the
    # script itself is shell source, and wrapping it in JSON would make it
    # unusable for the one thing it is for.
    context(ctx, output=output, assume_yes=assume_yes)

    completion_class = get_completion_class(shell)
    if completion_class is None:  # pragma: no cover - every SHELLS entry exists
        raise UnsupportedShellError(
            f"no completion support for {shell}",
            detail="Click implements bash, zsh, and fish.",
            docs=DOCS,
        )

    source = completion_class(
        cli=ctx.find_root().command,
        ctx_args={},
        prog_name="glean-idx",
        complete_var=COMPLETE_VAR,
    ).source()
    click.echo(source.strip())
    # On stderr so that redirecting stdout into a startup file captures only
    # the script.
    click.echo(f"Add it with: {INSTALL_HINTS[shell]}", err=True)
