"""Declarative preconditions for `glean-idx` commands.

A command states what it needs; the check runs before any work, so a missing
token or a wrong working directory fails in milliseconds with one consistent,
actionable message rather than part-way through a crawl.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any, Callable, TypeVar

import click

from glean.indexing.cli.context import CliContext
from glean.indexing.cli.errors import MissingCredentialsError
from glean.indexing.cli.main import context
from glean.indexing.cli.project import load_project_config, require_project

SERVER_URL_VAR = "GLEAN_SERVER_URL"
LEGACY_INSTANCE_VAR = "GLEAN_INSTANCE"
TOKEN_VAR = "GLEAN_INDEXING_API_TOKEN"

DOCS = "https://developers.glean.com/libraries/indexing-sdk/quickstart"

F = TypeVar("F", bound=Callable[..., Any])


def missing_credentials() -> list[str]:
    """Which of the required environment variables are unset."""
    missing = []
    if not os.getenv(SERVER_URL_VAR) and not os.getenv(LEGACY_INSTANCE_VAR):
        missing.append(SERVER_URL_VAR)
    if not os.getenv(TOKEN_VAR):
        missing.append(TOKEN_VAR)
    return missing


def check_credentials() -> None:
    """Fail unless Glean credentials are present in the environment."""
    missing = missing_credentials()
    if not missing:
        return
    noun = "variable" if len(missing) == 1 else "variables"
    raise MissingCredentialsError(
        f"missing required environment {noun}: {', '.join(missing)}",
        hint=[f"export {name}=..." for name in missing],
        docs=DOCS,
    )


def resolve_project(ctx: CliContext) -> Path:
    """Locate the project and cache it on the context."""
    if ctx.project_dir is None:
        ctx.project_dir = require_project(ctx.project_override)
        ctx.project_config = load_project_config(ctx.project_dir)
    return ctx.project_dir


def requires(
    *,
    credentials: bool = False,
    project: bool = False,
) -> Callable[[F], F]:
    """Declare what a command needs before it runs.

    Checked in order of how cheap they are to satisfy: credentials first, since
    a missing token is the most common problem and needs no filesystem work.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = click.get_current_context()
            # Resolve global flags before any check runs. A precondition that
            # fails first would otherwise render in the wrong output format,
            # and reading a context the command body has not created yet made
            # the project check silently skip itself.
            cli_ctx = context(
                ctx,
                output=_param(ctx, kwargs, "output"),
                assume_yes=bool(_param(ctx, kwargs, "assume_yes")),
                project_dir=_param(ctx, kwargs, "project_dir"),
            )
            if credentials:
                check_credentials()
            if project:
                resolve_project(cli_ctx)
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def _param(ctx: click.Context, kwargs: dict[str, Any], name: str) -> Any:
    """A parameter value, whether Click passed it as a kwarg or only on the context."""
    value = kwargs.get(name)
    return value if value is not None else ctx.params.get(name)


def project_option(func: F) -> F:
    """Add `--project`, for running against a project you are not inside."""
    return click.option(  # type: ignore[return-value]
        "--project",
        "project_dir",
        type=click.Path(file_okay=False, path_type=Path),
        default=None,
        help="Connector project directory. Defaults to searching upward from the cwd.",
    )(func)
