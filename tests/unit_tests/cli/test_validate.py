"""Tests for `glean-idx validate`."""

import json
from pathlib import Path

from click.testing import CliRunner

from glean.indexing.cli.commands.validate import validate
from glean.indexing.cli.errors import EXIT_VALIDATION

DOC_URL = "https://api.example.com/docs"


def run(connector_dir, *extra: str):
    """Invoke the command the way a caller would."""
    return CliRunner().invoke(validate, [str(connector_dir), *extra])


def test_validate_passes_with_confirmed_artifacts_and_auth(tmp_path):
    connector_dir = write_valid_connector_artifacts(tmp_path)

    assert run(connector_dir).exit_code == 0


def test_validate_requires_glean_directory(tmp_path):
    connector_dir = tmp_path / "example_connector"
    connector_dir.mkdir()

    assert run(connector_dir).exit_code == EXIT_VALIDATION


def test_validate_requires_confirmed_plan(tmp_path):
    connector_dir = write_valid_connector_artifacts(tmp_path)
    plan_path = connector_dir / ".glean/connector_plan.md"
    plan_path.write_text(
        plan_path.read_text().replace("Status: confirmed", "Status: not confirmed")
    )

    assert run(connector_dir).exit_code == EXIT_VALIDATION


def test_validate_requires_endpoint_inventory(tmp_path):
    connector_dir = write_valid_connector_artifacts(tmp_path)
    endpoints_path = connector_dir / ".glean/api_endpoints.json"
    endpoints = json.loads(endpoints_path.read_text())
    endpoints["endpoints"] = []
    endpoints_path.write_text(json.dumps(endpoints, indent=2) + "\n")

    assert run(connector_dir).exit_code == EXIT_VALIDATION


def test_validate_requires_test_and_production_auth(tmp_path):
    connector_dir = write_valid_connector_artifacts(tmp_path)
    plan_path = connector_dir / ".glean/connector_plan.md"
    plan_path.write_text(
        """# Example Connector Plan

## User Confirmation

- Status: confirmed

## Scope

Index source records as documents using a full crawl.

## Auth Plan

- Test auth: TBD
- Production auth: TBD
"""
    )
    investigation_path = connector_dir / ".glean/source_investigation.md"
    investigation_path.write_text(
        """# Example Source Investigation

## Auth

- Test auth: TBD
- Production auth: TBD

## API Behavior

The source API uses cursor pagination and has documented rate limits.
"""
    )

    assert run(connector_dir).exit_code == EXIT_VALIDATION


def test_validate_requires_sdk_usage_choice(tmp_path):
    connector_dir = write_valid_connector_artifacts(tmp_path)
    plan_path = connector_dir / ".glean/connector_plan.md"
    plan_path.write_text(
        plan_path.read_text().replace(
            "- SDK usage: Full connector flow using pull and push layers.\n", ""
        )
    )

    assert run(connector_dir).exit_code == EXIT_VALIDATION


def write_valid_connector_artifacts(tmp_path: Path) -> Path:
    connector_dir = tmp_path / "example_connector"
    artifact_dir = connector_dir / ".glean"
    artifact_dir.mkdir(parents=True)

    (artifact_dir / "source_docs.json").write_text(
        json.dumps(
            {
                "datasource": "example_connector",
                "display_name": "Example Connector",
                "confirmed_docs": [{"url": DOC_URL, "purpose": "source-of-truth"}],
            },
            indent=2,
        )
        + "\n"
    )
    (artifact_dir / "api_endpoints.json").write_text(
        json.dumps(
            {
                "datasource": "example_connector",
                "endpoints": [
                    {
                        "name": "List records",
                        "method": "GET",
                        "path": "/v1/records",
                        "purpose": "Fetch source records to index as documents",
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )
    (artifact_dir / "connector_plan.md").write_text(
        """# Example Connector Plan

## User Confirmation

- Status: confirmed

## Scope

Index source records as Glean documents using a full crawl. The first version excludes incremental sync and records it as developer follow-up work.

## SDK Usage

- SDK usage: Full connector flow using pull and push layers.

## Auth Plan

- Test auth: Temporary bearer token supplied through SOURCE_API_TOKEN during API exploration.
- Production auth: OAuth bearer token supplied by the connector deployment environment.
"""
    )
    (artifact_dir / "source_investigation.md").write_text(
        """# Example Source Investigation

## Auth

- Test auth: Temporary bearer token supplied through SOURCE_API_TOKEN.
- Production auth: OAuth bearer token from the production deployment secret store.

## API Behavior

The source API uses cursor pagination, has documented rate limits, and exposes records endpoints required for the confirmed full-crawl scope.
"""
    )
    (artifact_dir / "api_inventory.md").write_text(
        """# Example API Inventory

| Name | Method | Path | Purpose | Source |
| ---- | ------ | ---- | ------- | ------ |
| List records | GET | /v1/records | Fetch source records to index as documents | Source docs |
"""
    )
    return connector_dir


# --- the CLI surface ------------------------------------------------------


def test_valid_artifacts_emit_a_success_envelope(tmp_path):
    connector_dir = write_valid_connector_artifacts(tmp_path)
    result = run(connector_dir, "--output", "json")

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["valid"] is True
    assert payload["data"]["errors"] == []


def test_failures_arrive_as_a_list_an_agent_can_read(tmp_path):
    """One newline-joined blob would make the findings unusable programmatically."""
    connector_dir = write_valid_connector_artifacts(tmp_path)
    (connector_dir / ".glean/api_inventory.md").write_text("too short\n")
    (connector_dir / ".glean/source_docs.json").write_text(json.dumps({"datasource": "x"}) + "\n")

    result = run(connector_dir, "--output", "json")

    assert result.exit_code == EXIT_VALIDATION
    error = json.loads(result.output)["error"]
    assert error["code"] == "validation_failed"
    errors = error["data"]["errors"]
    assert isinstance(errors, list) and len(errors) >= 2
    assert any("confirmed_docs" in entry for entry in errors)
    assert any("substantive notes" in entry for entry in errors)


def test_every_problem_is_reported_in_one_pass(tmp_path):
    """Reporting only the first gap would make this gate a round-trip per fix."""
    connector_dir = tmp_path / "bare"
    (connector_dir / ".glean").mkdir(parents=True)

    result = run(connector_dir, "--output", "json")

    assert result.exit_code == EXIT_VALIDATION
    errors = json.loads(result.output)["error"]["data"]["errors"]
    assert sum(1 for entry in errors if entry.startswith("missing ")) == 5


def test_a_missing_artifact_directory_is_distinguished_from_bad_contents(tmp_path):
    """The likeliest mistake is running this in the wrong directory."""
    connector_dir = tmp_path / "no_artifacts"
    connector_dir.mkdir()

    result = run(connector_dir, "--output", "json")

    assert result.exit_code == EXIT_VALIDATION
    error = json.loads(result.output)["error"]
    assert "no connector artifacts" in error["message"]
    assert error["data"]["artifact_dir"].endswith(".glean")
    assert "errors" not in error["data"]


def test_the_connector_directory_defaults_to_the_working_directory(tmp_path, monkeypatch):
    connector_dir = write_valid_connector_artifacts(tmp_path)
    monkeypatch.chdir(connector_dir)

    result = CliRunner().invoke(validate, ["--output", "json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["valid"] is True


def test_the_failure_count_reads_correctly_for_one_problem(tmp_path):
    connector_dir = write_valid_connector_artifacts(tmp_path)
    (connector_dir / ".glean/api_inventory.md").unlink()

    result = run(connector_dir, "--output", "text")

    assert result.exit_code == EXIT_VALIDATION
    assert "1 problem in" in result.output
