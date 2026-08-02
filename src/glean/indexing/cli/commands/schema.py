"""`glean-idx schema` — the shape of what a connector has to produce.

`transform()` returns API models, and getting a field name or nesting wrong is
the most common way for a connector to upload something Glean rejects. Printing
the schema means neither a person nor an agent has to read the SDK's source to
find out what a document is allowed to contain.
"""

from __future__ import annotations

from typing import Any, Optional

import click

from glean.indexing.cli.errors import CliError, EXIT_USAGE
from glean.indexing.cli.main import context, global_options
from glean.indexing.cli.output import emit

DOCS = "https://developers.glean.com/libraries/indexing-sdk/models"

#: Short name -> the API model it describes. Named for what they are used for
#: rather than after the class, since that is what a caller is looking for.
MODELS: dict[str, str] = {
    "document": "DocumentDefinition",
    "datasource": "CustomDatasourceConfig",
    "employee": "EmployeeInfoDefinition",
    "user": "DatasourceUserDefinition",
    "group": "DatasourceGroupDefinition",
    "membership": "DatasourceBulkMembershipDefinition",
}


class UnknownSchemaError(CliError):
    """A name that is not one of the published schemas."""

    code = "unknown_schema"
    exit_code = EXIT_USAGE


@click.command()
@click.argument("name", required=False, metavar="[NAME]")
@global_options
@click.pass_context
def schema(
    ctx: click.Context,
    name: Optional[str],
    output: Optional[str],
    assume_yes: bool,
) -> None:
    """Print the JSON Schema for a connector's output models.

    With no NAME, lists what is available. Needs nothing from the environment,
    so it runs anywhere:

        uvx --from glean-indexing-sdk glean-idx schema document
    """
    cli_ctx = context(ctx, output=output, assume_yes=assume_yes)

    if name is None:
        data = {"schemas": {key: MODELS[key] for key in sorted(MODELS)}}
        emit(data, cli_ctx.output, text=_render_list(data["schemas"]))
        return

    model = _resolve(name)
    data = {"name": name, "model": MODELS[name], "schema": model.model_json_schema()}
    # No text rendering: a hand-summarized schema would be the one thing a
    # caller cannot act on, so both modes print the schema itself.
    emit(data, cli_ctx.output, text=None)


def _resolve(name: str) -> Any:
    """The API model class for a published schema name."""
    from glean.api_client import models

    if name not in MODELS:
        raise UnknownSchemaError(
            f"no schema named {name!r}",
            detail="Available: " + ", ".join(sorted(MODELS)),
            hint=["glean-idx schema    list every schema"],
            docs=DOCS,
        )
    return getattr(models, MODELS[name])


def _render_list(schemas: dict[str, str]) -> str:
    width = max(len(key) for key in schemas)
    lines = [f"  {key.ljust(width)}  {model}" for key, model in schemas.items()]
    return "\n".join([*lines, "", "  glean-idx schema <name>    print one schema"])
