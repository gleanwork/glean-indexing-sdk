"""Project discovery and connector loading, including every failure mode.

These messages are the main defence against the most likely way to be confused
by this CLI — running a project-scoped command from the wrong directory — so the
tests assert on the guidance, not just the exception type.
"""

import sys
import textwrap

import pytest

from glean.indexing.cli.errors import (
    EXIT_PRECONDITION,
    ConnectorNotImportableError,
    NoProjectError,
)
from glean.indexing.cli.project import (
    PROJECT_FILE,
    find_project,
    load_connector,
    load_project_config,
    require_project,
)

CONNECTOR_SOURCE = textwrap.dedent(
    """
    class MyConnector:
        name = "mine"

    class Helper:
        pass
    """
)


@pytest.fixture()
def project(tmp_path):
    """A minimal connector project on disk."""
    (tmp_path / PROJECT_FILE).write_text(
        "connector_name: wiki\nconnector_module: connector\nconnector_class: MyConnector\n"
    )
    (tmp_path / "connector.py").write_text(CONNECTOR_SOURCE)
    return tmp_path


def test_finds_the_project_in_the_current_directory(project):
    assert find_project(project) == project


def test_finds_the_project_from_a_subdirectory(project):
    nested = project / "a" / "b"
    nested.mkdir(parents=True)
    assert find_project(nested) == project


def test_returns_none_when_there_is_no_project(tmp_path):
    assert find_project(tmp_path) is None


def test_missing_project_names_every_directory_searched(tmp_path):
    with pytest.raises(NoProjectError) as excinfo:
        require_project(start=tmp_path)
    error = excinfo.value
    assert error.code == "no_project"
    assert error.exit_code == EXIT_PRECONDITION
    # The searched list is what makes this diagnosable rather than puzzling.
    assert str(tmp_path.resolve()) in error.searched
    assert any("cd <your connector project>" in hint for hint in error.hint)
    assert any("deploy init" in hint for hint in error.hint)


def test_project_override_is_used_when_valid(project, tmp_path):
    elsewhere = tmp_path / "unrelated"
    elsewhere.mkdir()
    assert require_project(override=project, start=elsewhere) == project


def test_project_override_pointing_nowhere_says_so(tmp_path):
    with pytest.raises(NoProjectError) as excinfo:
        require_project(override=tmp_path / "nope")
    assert "--project" in (excinfo.value.detail or "")


def test_malformed_project_file_reports_its_path(tmp_path):
    (tmp_path / PROJECT_FILE).write_text("connector_name: [unclosed\n")
    with pytest.raises(NoProjectError) as excinfo:
        load_project_config(tmp_path)
    assert PROJECT_FILE in excinfo.value.format_message()


def test_empty_project_file_parses_to_an_empty_mapping(tmp_path):
    (tmp_path / PROJECT_FILE).write_text("")
    assert load_project_config(tmp_path) == {}


def test_loads_the_connector_named_by_the_project_file(project):
    config = load_project_config(project)
    assert load_connector(project, config).name == "mine"


def test_project_directory_is_not_left_on_sys_path(project):
    before = list(sys.path)
    load_connector(project, load_project_config(project))
    assert sys.path == before


def test_explicit_reference_overrides_the_project_file(project):
    loaded = load_connector(project, {}, reference="connector:Helper")
    assert loaded.__name__ == "Helper"


def test_malformed_reference_shows_the_expected_shape(project):
    with pytest.raises(ConnectorNotImportableError) as excinfo:
        load_connector(project, {}, reference="connector")
    assert "module:Class" in (excinfo.value.detail or "")


def test_unknown_class_lists_what_the_module_does_define(project):
    with pytest.raises(ConnectorNotImportableError) as excinfo:
        load_connector(project, {}, reference="connector:Nope")
    detail = excinfo.value.detail or ""
    assert "MyConnector" in detail and "Helper" in detail


def test_missing_connector_class_in_config_is_explained(project):
    with pytest.raises(ConnectorNotImportableError) as excinfo:
        load_connector(project, {"connector_module": "connector"})
    assert "connector_class" in (excinfo.value.detail or "")


def test_absent_module_explains_the_environment_requirement(tmp_path):
    (tmp_path / PROJECT_FILE).write_text("connector_class: MyConnector\n")
    with pytest.raises(ConnectorNotImportableError) as excinfo:
        load_connector(tmp_path, load_project_config(tmp_path))
    detail = excinfo.value.detail or ""
    assert "same environment as your code" in detail
    assert any("uv run" in hint for hint in excinfo.value.hint)


def test_missing_transitive_dependency_is_distinguished(tmp_path):
    """A connector that imports successfully but lacks a dependency of its own
    is a different problem with a different fix, and must not be reported as a
    missing connector."""
    (tmp_path / PROJECT_FILE).write_text(
        "connector_module: connector\nconnector_class: MyConnector\n"
    )
    (tmp_path / "connector.py").write_text("import totally_absent_package\n")
    with pytest.raises(ConnectorNotImportableError) as excinfo:
        load_connector(tmp_path, load_project_config(tmp_path))
    message = excinfo.value.format_message()
    assert "totally_absent_package" in message
    assert any("totally_absent_package" in hint for hint in excinfo.value.hint)
