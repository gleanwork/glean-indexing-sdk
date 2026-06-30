import json
from pathlib import Path

from scripts.connector_builder.connector_builder import main


DOC_URL = "https://developer.webex.com/docs/api/v1/rooms/list-rooms"


def test_validate_passes_with_confirmed_artifacts_and_auth(tmp_path):
    connector_dir = write_valid_connector_artifacts(tmp_path)

    assert main(["validate", str(connector_dir)]) == 0


def test_validate_requires_glean_directory(tmp_path):
    connector_dir = tmp_path / "webex"
    connector_dir.mkdir()

    assert main(["validate", str(connector_dir)]) == 1


def test_validate_requires_confirmed_plan(tmp_path):
    connector_dir = write_valid_connector_artifacts(tmp_path)
    plan_path = connector_dir / ".glean/connector_plan.md"
    plan_path.write_text(plan_path.read_text().replace("Status: confirmed", "Status: not confirmed"))

    assert main(["validate", str(connector_dir)]) == 1


def test_validate_requires_endpoint_inventory(tmp_path):
    connector_dir = write_valid_connector_artifacts(tmp_path)
    endpoints_path = connector_dir / ".glean/api_endpoints.json"
    endpoints = json.loads(endpoints_path.read_text())
    endpoints["endpoints"] = []
    endpoints_path.write_text(json.dumps(endpoints, indent=2) + "\n")

    assert main(["validate", str(connector_dir)]) == 1


def test_validate_requires_test_and_production_auth(tmp_path):
    connector_dir = write_valid_connector_artifacts(tmp_path)
    plan_path = connector_dir / ".glean/connector_plan.md"
    plan_path.write_text(
        """# Webex Connector Plan

## User Confirmation

- Status: confirmed

## Scope

Index Webex rooms as documents using a full crawl.

## Auth Plan

- Test auth: TBD
- Production auth: TBD
"""
    )
    investigation_path = connector_dir / ".glean/source_investigation.md"
    investigation_path.write_text(
        """# Webex Source Investigation

## Auth

- Test auth: TBD
- Production auth: TBD

## API Behavior

The source API uses cursor pagination and has documented rate limits.
"""
    )

    assert main(["validate", str(connector_dir)]) == 1


def test_validate_requires_sdk_usage_choice(tmp_path):
    connector_dir = write_valid_connector_artifacts(tmp_path)
    plan_path = connector_dir / ".glean/connector_plan.md"
    plan_path.write_text(plan_path.read_text().replace("- SDK usage: Full connector flow using pull and push layers.\n", ""))

    assert main(["validate", str(connector_dir)]) == 1


def write_valid_connector_artifacts(tmp_path: Path) -> Path:
    connector_dir = tmp_path / "webex"
    artifact_dir = connector_dir / ".glean"
    artifact_dir.mkdir(parents=True)

    (artifact_dir / "source_docs.json").write_text(
        json.dumps(
            {
                "datasource": "webex",
                "display_name": "Webex",
                "confirmed_docs": [{"url": DOC_URL, "purpose": "source-of-truth"}],
            },
            indent=2,
        )
        + "\n"
    )
    (artifact_dir / "api_endpoints.json").write_text(
        json.dumps(
            {
                "datasource": "webex",
                "endpoints": [
                    {
                        "name": "List rooms",
                        "method": "GET",
                        "path": "/v1/rooms",
                        "purpose": "Fetch rooms to index as documents",
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )
    (artifact_dir / "connector_plan.md").write_text(
        """# Webex Connector Plan

## User Confirmation

- Status: confirmed

## Scope

Index rooms and messages as Glean documents using a full crawl. The first version excludes incremental sync and records it as developer follow-up work.

## SDK Usage

- SDK usage: Full connector flow using pull and push layers.

## Auth Plan

- Test auth: Webex developer PAT supplied through WEBEX_API_TOKEN during API exploration.
- Production auth: OAuth bearer token supplied by the connector deployment environment.
"""
    )
    (artifact_dir / "source_investigation.md").write_text(
        """# Webex Source Investigation

## Auth

- Test auth: Webex developer PAT supplied through WEBEX_API_TOKEN.
- Production auth: OAuth bearer token from the production deployment secret store.

## API Behavior

The source API uses cursor pagination, has documented rate limits, and exposes rooms and messages endpoints required for the confirmed full-crawl scope.
"""
    )
    (artifact_dir / "api_inventory.md").write_text(
        """# Webex API Inventory

| Name | Method | Path | Purpose | Source |
| ---- | ------ | ---- | ------- | ------ |
| List rooms | GET | /v1/rooms | Fetch rooms to index as documents | Webex docs |
"""
    )
    return connector_dir
