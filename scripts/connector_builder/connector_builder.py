"""Local helper tools for AI-built Glean Indexing SDK connectors."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any


ARTIFACT_DIR_NAME = ".glean"
REQUIRED_MARKDOWN_ARTIFACTS = ("connector_plan.md", "source_investigation.md", "api_inventory.md")
REQUIRED_JSON_ARTIFACTS = ("source_docs.json", "api_endpoints.json")


@dataclass(frozen=True)
class ConnectorNames:
    """Normalized names used by generated connector snippets."""

    datasource: str
    display_name: str
    class_prefix: str
    env_prefix: str


def main(argv: list[str] | None = None) -> int:
    """Run the connector-builder CLI."""
    parser = argparse.ArgumentParser(description="Initialize, validate, and generate AI-built connector workspaces.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create .glean planning artifacts")
    init_parser.add_argument("datasource", help="Datasource name, for example webex")
    init_parser.add_argument("--display-name", help="Human-readable datasource name")
    init_parser.add_argument("--doc-url", action="append", default=[], help="Confirmed source documentation URL. May be passed more than once.")
    init_parser.add_argument("--workspace-dir", default=".", help="Connector workspace directory. Defaults to the current directory.")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing generated artifacts")
    init_parser.set_defaults(func=init_workspace)

    validate_parser = subparsers.add_parser("validate", help="Validate .glean planning artifacts")
    validate_parser.add_argument("--workspace-dir", default=".", help="Connector workspace directory. Defaults to the current directory.")
    validate_parser.set_defaults(func=validate_workspace)

    generate_parser = subparsers.add_parser("generate", help="Create a local snippets/<datasource> connector skeleton")
    generate_parser.add_argument("datasource", help="Datasource name, for example webex")
    generate_parser.add_argument("--display-name", help="Human-readable datasource name")
    generate_parser.add_argument("--workspace-dir", default=".", help="Connector workspace directory. Defaults to the current directory.")
    generate_parser.add_argument("--force", action="store_true", help="Overwrite existing snippet files")
    generate_parser.set_defaults(func=generate_connector)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ConnectorBuilderError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


def init_workspace(args: argparse.Namespace) -> None:
    """Create connector planning artifacts for an agent-guided build."""
    names = normalize_names(args.datasource, args.display_name)
    artifact_dir = artifact_dir_for(args.workspace_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    write_json(
        artifact_dir / "source_docs.json",
        {
            "datasource": names.datasource,
            "display_name": names.display_name,
            "confirmed_docs": [{"url": url, "purpose": "source-of-truth"} for url in args.doc_url],
            "notes": [],
        },
        force=args.force,
    )
    write_text(artifact_dir / "connector_plan.md", connector_plan_template(names), force=args.force)
    write_text(artifact_dir / "source_investigation.md", source_investigation_template(names), force=args.force)
    write_text(artifact_dir / "api_inventory.md", api_inventory_template(names), force=args.force)
    write_json(
        artifact_dir / "api_endpoints.json",
        {
            "datasource": names.datasource,
            "base_url": "",
            "endpoints": [],
            "pagination": {"strategy": "", "cursor_field": ""},
            "rate_limits": {"documented_limits": "", "retry_headers": []},
            "permissions": [],
        },
        force=args.force,
    )
    write_text(artifact_dir / "api_calls_log.md", api_calls_log_template(names), force=args.force)
    print(f"Initialized connector workspace for {names.datasource} at {artifact_dir}")


def validate_workspace(args: argparse.Namespace) -> None:
    """Validate that required planning artifacts exist and have expected structure."""
    artifact_dir = artifact_dir_for(args.workspace_dir)
    errors: list[str] = []

    for filename in (*REQUIRED_JSON_ARTIFACTS, *REQUIRED_MARKDOWN_ARTIFACTS):
        path = artifact_dir / filename
        if not path.exists():
            errors.append(f"missing {path}")

    source_docs = read_json_artifact(artifact_dir / "source_docs.json", errors)
    if source_docs is not None:
        require_string(source_docs, "datasource", artifact_dir / "source_docs.json", errors)
        docs = source_docs.get("confirmed_docs")
        if not isinstance(docs, list) or not docs:
            errors.append(f"{artifact_dir / 'source_docs.json'} must contain at least one confirmed_docs entry")
        elif not all(isinstance(doc, dict) and isinstance(doc.get("url"), str) and doc["url"] for doc in docs):
            errors.append(f"{artifact_dir / 'source_docs.json'} confirmed_docs entries must include non-empty url strings")

    endpoints = read_json_artifact(artifact_dir / "api_endpoints.json", errors)
    if endpoints is not None:
        require_string(endpoints, "datasource", artifact_dir / "api_endpoints.json", errors)
        endpoint_list = endpoints.get("endpoints")
        if not isinstance(endpoint_list, list) or not endpoint_list:
            errors.append(f"{artifact_dir / 'api_endpoints.json'} endpoints must be a non-empty list")
        else:
            for index, endpoint in enumerate(endpoint_list):
                validate_endpoint(endpoint, index, artifact_dir / "api_endpoints.json", errors)

    for filename in REQUIRED_MARKDOWN_ARTIFACTS:
        path = artifact_dir / filename
        if path.exists() and len(path.read_text(encoding="utf-8").strip()) < 80:
            errors.append(f"{path} must contain substantive notes")

    plan_path = artifact_dir / "connector_plan.md"
    if plan_path.exists() and "Status: confirmed" not in plan_path.read_text(encoding="utf-8"):
        errors.append(f"{plan_path} must include user confirmation with `Status: confirmed`")

    if errors:
        raise ConnectorBuilderError("\n".join(errors))

    print("Connector workspace validation passed")


def generate_connector(args: argparse.Namespace) -> None:
    """Create a compilable snippet skeleton for connector implementation."""
    names = normalize_names(args.datasource, args.display_name)
    workspace_dir = Path(args.workspace_dir)
    snippet_dir = workspace_dir / "snippets" / names.datasource
    snippet_dir.mkdir(parents=True, exist_ok=True)

    files = {
        snippet_dir / f"{names.datasource}_data.py": render(DATA_TEMPLATE, names),
        snippet_dir / f"{names.datasource}_data_client.py": render(DATA_CLIENT_TEMPLATE, names),
        snippet_dir / f"{names.datasource}_connector.py": render(CONNECTOR_TEMPLATE, names),
        snippet_dir / "run_connector.py": render(RUN_CONNECTOR_TEMPLATE, names),
        snippet_dir / ".env.example": render(ENV_TEMPLATE, names),
    }

    for path, content in files.items():
        write_text(path, content, force=args.force)

    print(f"Created connector snippet skeleton in {snippet_dir}")


def artifact_dir_for(workspace_dir: str) -> Path:
    """Return the .glean artifact directory for a connector workspace."""
    return Path(workspace_dir) / ARTIFACT_DIR_NAME


def normalize_names(datasource: str, display_name: str | None) -> ConnectorNames:
    """Normalize user-provided connector names."""
    normalized = re.sub(r"[^a-z0-9]+", "_", datasource.strip().lower()).strip("_")
    if not normalized:
        raise ConnectorBuilderError("datasource must contain at least one letter or number")

    words = [part for part in normalized.split("_") if part]
    class_prefix = "".join(word.capitalize() for word in words)
    return ConnectorNames(
        datasource=normalized,
        display_name=display_name or " ".join(word.capitalize() for word in words),
        class_prefix=class_prefix,
        env_prefix=normalized.upper(),
    )


def write_json(path: Path, payload: dict[str, Any], *, force: bool) -> None:
    """Write a formatted JSON file unless it already exists."""
    write_text(path, json.dumps(payload, indent=2) + "\n", force=force)


def write_text(path: Path, content: str, *, force: bool) -> None:
    """Write a text file, preserving existing files unless forced."""
    if path.exists() and not force:
        raise ConnectorBuilderError(f"{path} already exists; pass --force to overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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


def render(template: str, names: ConnectorNames) -> str:
    """Render a text template with connector names."""
    return Template(template).substitute(
        datasource=names.datasource,
        display_name=names.display_name,
        class_prefix=names.class_prefix,
        env_prefix=names.env_prefix,
    )


def connector_plan_template(names: ConnectorNames) -> str:
    """Return the user-facing connector plan template."""
    return f"""# {names.display_name} Connector Plan

## User Goal

Build a {names.display_name} connector for datasource `{names.datasource}`.

## Proposed Scope

- Content to index:
- Identities to sync:
- Permissions to preserve:
- Crawl mode:
- Deployment ownership:

## Product Constraints

- Full crawl only if:
- Incremental crawl possible if:
- Push-layer-only option:
- Hosted deployment option:

## Open Questions For User

- [ ] Which entities should be included in the first version?
- [ ] Should this use only the push layer, or the full connector flow?
- [ ] Should deployment/hosting be included, or only local connector code?

## User Confirmation

- Status: not confirmed
- Confirmed scope:
"""


def source_investigation_template(names: ConnectorNames) -> str:
    """Return the source investigation markdown template."""
    return f"""# {names.display_name} Source Investigation

## Source Documentation

- Confirmed docs:
- Confidence notes:

## Auth

- Auth method:
- Required scopes:
- Test credential path:
- Production credential path:

## Data Model

- Source objects:
- Identity objects:
- Document objects:

## Sync Behavior

- Full crawl:
- Incremental crawl:
- Deletions:
- Checkpoint:

## API Behavior

- Pagination:
- Rate limits:
- Retries:
- Permissions:

## Unknowns

- [ ] Replace this checklist with resolved questions before implementation.
"""


def api_inventory_template(names: ConnectorNames) -> str:
    """Return the API inventory markdown template."""
    return f"""# {names.display_name} API Inventory

Use this file for the cited endpoint catalog produced by API exploration.

## Endpoint Summary

| Name | Method | Path | Purpose | Source |
| ---- | ------ | ---- | ------- | ------ |

## Live Read-Only Probing Notes

- Credentials used:
- Redaction policy:
- Calls attempted:
- Calls skipped:

## Connector-Relevant Findings

- Auth:
- Pagination:
- Incremental filters:
- Rate limits:
- Permissions:
- Deletions:
"""


def api_calls_log_template(names: ConnectorNames) -> str:
    """Return the API calls log template."""
    return f"""# {names.display_name} API Calls Log

Record read-only API probes here. Redact all secrets before writing commands or headers.

| Endpoint | Status | Notes |
| -------- | ------ | ----- |
"""


DATA_TEMPLATE = '''"""Source data shapes for the $display_name connector."""

from typing import TypedDict


class ${class_prefix}Item(TypedDict):
    """Minimal source object. Replace with fields from confirmed source docs."""

    id: str
    title: str
    url: str
    body: str
'''


DATA_CLIENT_TEMPLATE = '''"""Source API client for the $display_name connector."""

import os
from typing import Optional, Sequence

from glean.indexing.connectors import BaseDataClient

from .${datasource}_data import ${class_prefix}Item


class ${class_prefix}DataClient(BaseDataClient[${class_prefix}Item]):
    """Fetch source data for $display_name."""

    def __init__(self, base_url: str, api_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token

    @classmethod
    def from_env(cls) -> "${class_prefix}DataClient":
        """Create a client from environment variables."""
        return cls(
            base_url=os.environ["${env_prefix}_BASE_URL"],
            api_token=os.environ["${env_prefix}_API_TOKEN"],
        )

    def get_source_data(self, since: Optional[str] = None) -> Sequence[${class_prefix}Item]:
        """Fetch source data.

        Replace this placeholder with calls to the confirmed endpoints in `.glean/api_endpoints.json`.
        """
        _ = since
        return []
'''


CONNECTOR_TEMPLATE = '''"""Glean connector for $display_name."""

from typing import List, Sequence

from glean.indexing.connectors import BaseDatasourceConnector
from glean.indexing.models import ContentDefinition, CustomDatasourceConfig, DocumentDefinition

from .${datasource}_data import ${class_prefix}Item


class ${class_prefix}Connector(BaseDatasourceConnector[${class_prefix}Item]):
    """Transform $display_name source objects into Glean documents."""

    configuration: CustomDatasourceConfig = CustomDatasourceConfig(
        name="$datasource",
        display_name="$display_name",
        is_user_referenced_by_email=True,
    )

    def transform(self, data: Sequence[${class_prefix}Item]) -> List[DocumentDefinition]:
        """Transform source objects into Glean document definitions."""
        return [
            DocumentDefinition(
                id=item["id"],
                title=item["title"],
                datasource=self.name,
                view_url=item["url"],
                body=ContentDefinition(mime_type="text/plain", text_content=item["body"]),
            )
            for item in data
        ]
'''


RUN_CONNECTOR_TEMPLATE = '''"""Run the $display_name connector snippet."""

from glean.indexing.models import IndexingMode

from .${datasource}_connector import ${class_prefix}Connector
from .${datasource}_data_client import ${class_prefix}DataClient


def main() -> None:
    """Run a full crawl for local validation."""
    connector = ${class_prefix}Connector(name="$datasource", data_client=${class_prefix}DataClient.from_env())
    connector.configure_datasource()
    connector.index_data(mode=IndexingMode.FULL)


if __name__ == "__main__":
    main()
'''


ENV_TEMPLATE = """# Source API credentials
${env_prefix}_BASE_URL=https://api.example.com
${env_prefix}_API_TOKEN=

# Glean indexing credentials
GLEAN_SERVER_URL=https://example-be.glean.com
GLEAN_INDEXING_API_TOKEN=
"""


class ConnectorBuilderError(Exception):
    """Raised for expected connector-builder CLI failures."""


if __name__ == "__main__":
    raise SystemExit(main())
