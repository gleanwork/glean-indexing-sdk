"""CLI regressions for successful live status responses."""

import json
from pathlib import Path
from unittest.mock import patch

import httpx
from click.testing import CliRunner

from glean.api_client import Glean
from glean.indexing.cli.commands.datasource import datasource
from glean.indexing.cli.commands.document import document

_FIXTURES = Path(__file__).parents[2] / "fixtures" / "status"


def _generated_client(body: str) -> Glean:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=body,
            headers={"Content-Type": "application/json"},
            request=request,
        )

    return Glean(
        api_token="test-token",
        server_url="https://example-be.glean.com",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _credentials(monkeypatch) -> None:
    monkeypatch.setenv("GLEAN_SERVER_URL", "https://example-be.glean.com")
    monkeypatch.setenv("GLEAN_INDEXING_API_TOKEN", "test-token")


def test_datasource_status_cli_accepts_live_application_json_response(monkeypatch):
    _credentials(monkeypatch)
    client = _generated_client((_FIXTURES / "datasource_status_200.json").read_text())

    with patch("glean.indexing.push.uploader.api_client", return_value=client):
        result = CliRunner().invoke(
            datasource,
            ["status", "--datasource", "smoketest", "--output", "json"],
        )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["documents"]["indexed"] == {"smokeDocument": 2}


def test_document_status_poll_cli_accepts_already_indexed_live_response(monkeypatch):
    _credentials(monkeypatch)
    client = _generated_client((_FIXTURES / "document_status_200.json").read_text())

    with patch("glean.indexing.push.uploader.api_client", return_value=client):
        result = CliRunner().invoke(
            document,
            [
                "status",
                "--datasource",
                "smoketest",
                "--document",
                "smokeDocument",
                "document-a",
                "--poll",
                "--output",
                "json",
            ],
        )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["result"] == "indexed"
