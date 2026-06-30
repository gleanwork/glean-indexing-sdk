"""Validation gate for AI-built connector planning artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_MARKDOWN_ARTIFACTS = ("connector_plan.md", "source_investigation.md", "api_inventory.md")
REQUIRED_JSON_ARTIFACTS = ("source_docs.json", "api_endpoints.json")
TEST_AUTH_LABELS = ("test auth", "testing auth", "api exploration auth", "test auth used during api exploration")
PROD_AUTH_LABELS = ("production auth", "prod auth", "production source auth")


def main(argv: list[str] | None = None) -> int:
    """Run the connector-builder validator."""
    parser = argparse.ArgumentParser(description="Validate AI-built connector planning artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate a connector folder's .glean artifacts")
    validate_parser.add_argument("connector_dir", nargs="?", default=".", help="Connector folder containing a .glean directory")
    validate_parser.set_defaults(func=validate_workspace)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ConnectorBuilderError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


def validate_workspace(args: argparse.Namespace) -> None:
    """Validate that connector planning artifacts are ready for implementation."""
    connector_dir = Path(args.connector_dir)
    artifact_dir = connector_dir / ".glean"
    errors: list[str] = []

    if not artifact_dir.is_dir():
        raise ConnectorBuilderError(f"missing connector artifact directory {artifact_dir}")

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

    plan_text = read_text_if_exists(artifact_dir / "connector_plan.md")
    investigation_text = read_text_if_exists(artifact_dir / "source_investigation.md")
    combined_text = f"{plan_text}\n{investigation_text}"

    if plan_text and "status: confirmed" not in plan_text.lower():
        errors.append(f"{artifact_dir / 'connector_plan.md'} must include user confirmation with `Status: confirmed`")

    if not has_filled_label(combined_text, TEST_AUTH_LABELS):
        errors.append("auth information must specify the test/API-exploration auth flow")
    if not has_filled_label(combined_text, PROD_AUTH_LABELS):
        errors.append("auth information must specify the production source auth flow")

    if errors:
        raise ConnectorBuilderError("\n".join(errors))

    print("Connector workspace validation passed")


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
    return bool(normalized) and normalized not in {"tbd", "todo", "unknown", "n/a", "none", "<redacted>"}


class ConnectorBuilderError(Exception):
    """Raised for expected connector-builder validation failures."""


if __name__ == "__main__":
    raise SystemExit(main())
