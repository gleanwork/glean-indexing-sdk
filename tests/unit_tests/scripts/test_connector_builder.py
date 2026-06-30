import json
import py_compile
from pathlib import Path

from scripts.connector_builder.connector_builder import main


DOC_URL = "https://developer.webex.com/docs/api/v1/rooms/list-rooms"


def test_init_creates_planning_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = main(["init", "webex", "--display-name", "Webex", "--doc-url", DOC_URL])

    assert result == 0
    assert Path(".glean/source_docs.json").exists()
    assert Path(".glean/source_investigation.md").exists()
    assert Path(".glean/api_inventory.md").exists()
    assert Path(".glean/api_endpoints.json").exists()
    assert Path(".glean/api_calls_log.md").exists()
    assert Path(".glean/external_docs").is_dir()
    assert not Path(".glean/connector_plan.md").exists()


def test_validate_requires_confirmed_plan_and_endpoint_inventory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    main(["init", "webex", "--doc-url", DOC_URL])

    assert main(["validate"]) == 1

    plan_path = Path(".glean/connector_plan.md")
    plan_path.write_text(
        """# Webex Connector Plan

## User Confirmation

- Status: confirmed

## Scope

Index Webex rooms as documents using a full crawl.
"""
    )

    endpoints_path = Path(".glean/api_endpoints.json")
    endpoints = json.loads(endpoints_path.read_text())
    endpoints["endpoints"] = [
        {
            "name": "List rooms",
            "method": "GET",
            "path": "/v1/rooms",
            "purpose": "Fetch rooms to index as documents",
        }
    ]
    endpoints_path.write_text(json.dumps(endpoints, indent=2) + "\n")

    assert main(["validate"]) == 0


def test_validate_requires_confirmed_docs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    main(["init", "webex"])

    assert main(["validate"]) == 1


def test_generate_creates_compilable_snippet(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = main(["generate", "webex", "--display-name", "Webex"])

    assert result == 0
    snippet_dir = Path("snippets/webex")
    expected_files = [
        snippet_dir / "webex_data.py",
        snippet_dir / "webex_data_client.py",
        snippet_dir / "webex_connector.py",
        snippet_dir / "run_connector.py",
        snippet_dir / ".env.example",
    ]
    for path in expected_files:
        assert path.exists()

    for path in snippet_dir.glob("*.py"):
        py_compile.compile(str(path), doraise=True)
