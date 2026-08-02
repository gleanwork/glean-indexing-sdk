"""`glean-idx validate` — the gate between planning a connector and building one.

The artifacts under a connector's `.glean/` directory are what an agent and a
person agreed the connector would do. This checks they are complete, filled in,
and confirmed before any implementation code gets written.

Shipped as part of the CLI rather than as a repository script because the agent
skills that call it are distributed as a plugin: the machine running them has the
SDK installed, not a checkout of this repository.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import click

from glean.indexing.cli.errors import ValidationFailedError
from glean.indexing.cli.main import context, global_options
from glean.indexing.cli.output import emit

DOCS = "https://developers.glean.com/libraries/indexing-sdk/connector-builder"

ARTIFACT_DIR = ".glean"
REQUIRED_MARKDOWN_ARTIFACTS = ("connector_plan.md", "source_investigation.md", "api_inventory.md")
REQUIRED_JSON_ARTIFACTS = ("source_docs.json", "api_endpoints.json")
TEST_AUTH_LABELS = (
    "test auth",
    "testing auth",
    "api exploration auth",
    "test auth used during api exploration",
)
PROD_AUTH_LABELS = ("production auth", "prod auth", "production source auth")
SDK_USAGE_LABELS = ("sdk usage", "sdk feature usage", "sdk mode", "sdk features")


@click.command()
@click.argument(
    "connector_dir",
    default=".",
    type=click.Path(file_okay=False, path_type=Path),
    metavar="[CONNECTOR_DIR]",
)
@global_options
@click.pass_context
def validate(
    ctx: click.Context,
    connector_dir: Path,
    output: Optional[str],
    assume_yes: bool,
) -> None:
    """Check a connector's planning artifacts before implementation.

    Needs nothing but the directory, so it runs anywhere:

        uvx --from glean-indexing-sdk glean-idx validate ./my-connector
    """
    cli_ctx = context(ctx, output=output, assume_yes=assume_yes)
    artifact_dir = connector_dir / ARTIFACT_DIR

    if not artifact_dir.is_dir():
        raise ValidationFailedError(
            f"no connector artifacts at {artifact_dir}",
            detail=("Planning artifacts live in the connector folder, not at the repository root."),
            hint=[f"mkdir -p {artifact_dir}", "then run the connector-builder skill"],
            docs=DOCS,
            data={"connector_dir": str(connector_dir), "artifact_dir": str(artifact_dir)},
        )

    errors = collect_errors(artifact_dir)
    data = {
        "connector_dir": str(connector_dir),
        "artifact_dir": str(artifact_dir),
        "valid": not errors,
        "errors": errors,
    }

    # Reported as a failure, not a report of one: an agent branching on `ok`
    # has to be stopped by an incomplete plan, which is the whole point of a
    # gate. The findings travel in `data` so nothing measured is lost.
    if errors:
        raise ValidationFailedError(
            f"{len(errors)} problem{'' if len(errors) == 1 else 's'} in {artifact_dir}",
            detail="\n".join(f"  - {error}" for error in errors),
            hint=["fix the artifacts above, then re-run this command"],
            docs=DOCS,
            data=data,
        )

    emit(data, cli_ctx.output, text=f"  {artifact_dir} is complete and confirmed.")


def collect_errors(artifact_dir: Path) -> list[str]:
    """Every problem with a connector's planning artifacts, in reading order.

    Returns findings rather than raising on the first one: a half-finished plan
    usually has several gaps, and fixing them one round-trip at a time is the
    slowest way to get through this gate.
    """
    errors: list[str] = []

    for filename in (*REQUIRED_JSON_ARTIFACTS, *REQUIRED_MARKDOWN_ARTIFACTS):
        path = artifact_dir / filename
        if not path.exists():
            errors.append(f"missing {path}")
        elif path.stat().st_size == 0:
            errors.append(f"{path} must not be empty")

    source_docs = read_json_artifact(artifact_dir / "source_docs.json", errors)
    if source_docs is not None:
        require_string(source_docs, "datasource", artifact_dir / "source_docs.json", errors)
        docs = source_docs.get("confirmed_docs")
        if not isinstance(docs, list) or not docs:
            errors.append(
                f"{artifact_dir / 'source_docs.json'} must contain at least one confirmed_docs entry"
            )
        elif not all(
            isinstance(doc, dict) and isinstance(doc.get("url"), str) and doc["url"] for doc in docs
        ):
            errors.append(
                f"{artifact_dir / 'source_docs.json'} confirmed_docs entries must include non-empty url strings"
            )

    endpoints = read_json_artifact(artifact_dir / "api_endpoints.json", errors)
    if endpoints is not None:
        require_string(endpoints, "datasource", artifact_dir / "api_endpoints.json", errors)
        endpoint_list = endpoints.get("endpoints")
        if not isinstance(endpoint_list, list) or not endpoint_list:
            errors.append(
                f"{artifact_dir / 'api_endpoints.json'} endpoints must be a non-empty list"
            )
        else:
            for index, endpoint in enumerate(endpoint_list):
                validate_endpoint(endpoint, index, artifact_dir / "api_endpoints.json", errors)

    for filename in REQUIRED_MARKDOWN_ARTIFACTS:
        path = artifact_dir / filename
        if path.exists() and len(path.read_text(encoding="utf-8").strip()) < 80:
            errors.append(f"{path} must contain substantive notes")

    plan_text = read_text_if_exists(artifact_dir / "connector_plan.md")
    investigation_text = read_text_if_exists(artifact_dir / "source_investigation.md")
    combined_text = f"{plan_text}\n{investigation_text}"

    if plan_text and "status: confirmed" not in plan_text.lower():
        errors.append(
            f"{artifact_dir / 'connector_plan.md'} must include user confirmation with `Status: confirmed`"
        )

    if not has_filled_label(combined_text, TEST_AUTH_LABELS):
        errors.append("auth information must specify the test/API-exploration auth flow")
    if not has_filled_label(combined_text, PROD_AUTH_LABELS):
        errors.append("auth information must specify the production source auth flow")
    if not has_filled_label(plan_text, SDK_USAGE_LABELS):
        errors.append("connector plan must specify the confirmed SDK usage mode")

    return errors


def read_json_artifact(path: Path, errors: list[str]) -> dict[str, Any] | None:
    """Read a JSON artifact and collect validation errors."""
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        errors.append(f"{path} is not valid JSON: {error}")
        return None
    if not isinstance(value, dict):
        errors.append(f"{path} must contain a JSON object")
        return None
    return value


def read_text_if_exists(path: Path) -> str:
    """Read a text file if it exists."""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def require_string(payload: dict[str, Any], key: str, path: Path, errors: list[str]) -> None:
    """Require a non-empty string field in a JSON object."""
    if not isinstance(payload.get(key), str) or not payload[key]:
        errors.append(f"{path} must include non-empty string field {key!r}")


def validate_endpoint(endpoint: Any, index: int, path: Path, errors: list[str]) -> None:
    """Validate one endpoint inventory entry."""
    if not isinstance(endpoint, dict):
        errors.append(f"{path} endpoints[{index}] must be an object")
        return
    for key in ("name", "method", "path", "purpose"):
        if not isinstance(endpoint.get(key), str) or not endpoint[key]:
            errors.append(f"{path} endpoints[{index}] must include non-empty {key!r}")


def has_filled_label(text: str, labels: tuple[str, ...]) -> bool:
    """Return whether text has a non-placeholder value for any label."""
    for line in text.splitlines():
        normalized = line.strip().lstrip("-*").strip()
        if ":" not in normalized:
            continue
        label, value = normalized.split(":", 1)
        if label.strip().lower() not in labels:
            continue
        if is_substantive_value(value):
            return True
    return False


def is_substantive_value(value: str) -> bool:
    """Return whether an artifact field value looks filled in."""
    normalized = value.strip().lower()
    return bool(normalized) and normalized not in {
        "tbd",
        "todo",
        "unknown",
        "n/a",
        "none",
        "<redacted>",
    }
