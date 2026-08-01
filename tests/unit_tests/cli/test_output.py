"""Output-mode resolution and envelope shape."""

import json

import pytest

from glean.indexing.cli.errors import EXIT_PRECONDITION, MissingCredentialsError
from glean.indexing.cli.output import (
    OutputMode,
    default_output_mode,
    emit,
    render_error,
    resolve_output_mode,
)


def test_default_is_text_at_a_terminal(monkeypatch):
    monkeypatch.setattr("sys.stdout.isatty", lambda: True, raising=False)
    assert default_output_mode() is OutputMode.TEXT


def test_default_is_json_when_redirected(monkeypatch):
    monkeypatch.setattr("sys.stdout.isatty", lambda: False, raising=False)
    assert default_output_mode() is OutputMode.JSON


@pytest.mark.parametrize("explicit", ["text", "json"])
def test_explicit_output_wins_over_detection(explicit, monkeypatch):
    monkeypatch.setattr("sys.stdout.isatty", lambda: True, raising=False)
    assert resolve_output_mode(explicit) is OutputMode(explicit)


def test_success_envelope_is_stable(capsys):
    emit({"count": 2}, OutputMode.JSON)
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": True, "data": {"count": 2}}


def test_text_mode_prefers_the_human_rendering(capsys):
    emit({"count": 2}, OutputMode.TEXT, text="two things")
    assert capsys.readouterr().out.strip() == "two things"


def test_text_mode_falls_back_to_json_rather_than_printing_nothing(capsys):
    emit({"count": 2}, OutputMode.TEXT)
    assert json.loads(capsys.readouterr().out) == {"count": 2}


def test_error_envelope_carries_a_machine_readable_code():
    error = MissingCredentialsError("nope", hint=["do this"], docs="https://x", data={"a": 1})
    payload = json.loads(render_error(error, OutputMode.JSON))
    assert payload["ok"] is False
    assert payload["error"]["code"] == "missing_credentials"
    assert payload["error"]["hint"] == ["do this"]
    assert payload["error"]["data"] == {"a": 1}


def test_error_text_names_the_code_and_the_fix():
    error = MissingCredentialsError("nope", hint=["export FOO=..."], docs="https://x")
    rendered = render_error(error, OutputMode.TEXT)
    assert "[missing_credentials]" in rendered
    assert "export FOO=..." in rendered
    assert "https://x" in rendered


def test_precondition_failures_share_one_exit_code():
    assert MissingCredentialsError("nope").exit_code == EXIT_PRECONDITION
