"""Tests for `glean-idx schema`."""

import json

from click.testing import CliRunner

from glean.indexing.cli.commands.schema import MODELS, schema
from glean.indexing.cli.errors import EXIT_USAGE


def test_listing_names_every_published_schema():
    result = CliRunner().invoke(schema, ["--output", "json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["data"]["schemas"] == dict(sorted(MODELS.items()))


def test_a_named_schema_is_the_real_json_schema():
    result = CliRunner().invoke(schema, ["document", "--output", "json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)["data"]
    assert data["model"] == "DocumentDefinition"
    assert data["schema"]["required"] == ["datasource"]
    assert "title" in data["schema"]["properties"]


def test_every_published_name_resolves_to_a_real_model():
    """A typo in the table would only surface when someone asked for that name."""
    runner = CliRunner()
    for name in MODELS:
        result = runner.invoke(schema, [name, "--output", "json"])
        assert result.exit_code == 0, f"{name}: {result.output}"
        assert json.loads(result.stdout)["data"]["schema"]["properties"]


def test_an_unknown_name_lists_the_real_ones():
    result = CliRunner().invoke(schema, ["nope", "--output", "json"])

    assert result.exit_code == EXIT_USAGE
    error = json.loads(result.stdout)["error"]
    assert error["code"] == "unknown_schema"
    assert "document" in error["detail"]


def test_text_mode_still_prints_the_schema_itself():
    """A summarized schema would be the one thing a caller cannot act on."""
    result = CliRunner().invoke(schema, ["document", "--output", "text"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["schema"]["properties"]


def test_the_command_needs_nothing_from_the_environment(monkeypatch):
    monkeypatch.delenv("GLEAN_SERVER_URL", raising=False)
    monkeypatch.delenv("GLEAN_INDEXING_API_TOKEN", raising=False)

    assert CliRunner().invoke(schema, ["document"]).exit_code == 0
