"""Tests for project and connector discovery."""

import tempfile
from pathlib import Path

import pytest

from glean.indexing.worker.discovery import ConnectorInfo, ProjectDiscovery, ProjectInfo


class TestProjectDiscovery:
    """Tests for ProjectDiscovery class."""

    def test_discover_project_basic(self, tmp_path: Path):
        """Test discovering basic project info."""
        # Create a minimal project structure
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test-connector'")

        discovery = ProjectDiscovery(tmp_path)
        info = discovery.discover_project()

        assert info.path == str(tmp_path)
        assert info.name == tmp_path.name
        assert info.has_pyproject is True
        assert info.has_mock_data is False

    def test_discover_project_with_mock_data(self, tmp_path: Path):
        """Test discovering project with mock data."""
        (tmp_path / "pyproject.toml").write_text("[project]")
        (tmp_path / "mock_data.json").write_text('[{"id": 1}]')

        discovery = ProjectDiscovery(tmp_path)
        info = discovery.discover_project()

        assert info.has_mock_data is True
        assert info.mock_data_path == str(tmp_path / "mock_data.json")

    def test_discover_project_test_data(self, tmp_path: Path):
        """Test discovering project with test_data.json."""
        (tmp_path / "pyproject.toml").write_text("[project]")
        (tmp_path / "test_data.json").write_text('[{"id": 1}]')

        discovery = ProjectDiscovery(tmp_path)
        info = discovery.discover_project()

        assert info.has_mock_data is True
        assert "test_data.json" in info.mock_data_path

    def test_discover_connectors_empty_project(self, tmp_path: Path):
        """Test discovering connectors in empty project."""
        discovery = ProjectDiscovery(tmp_path)
        connectors = discovery.discover_connectors()
        assert connectors == []

    def test_discover_connectors_by_base_class(self, tmp_path: Path):
        """Test discovering connector by base class name."""
        connector_code = '''
from glean.indexing.connectors import BaseDatasourceConnector

class MyConnector(BaseDatasourceConnector):
    """A test connector."""

    def get_data(self):
        return []

    def transform(self, data):
        return []
'''
        (tmp_path / "connector.py").write_text(connector_code)

        discovery = ProjectDiscovery(tmp_path)
        connectors = discovery.discover_connectors()

        assert len(connectors) == 1
        assert connectors[0].class_name == "MyConnector"
        assert "BaseDatasourceConnector" in connectors[0].base_classes
        assert connectors[0].docstring == "A test connector."

    def test_discover_connectors_by_methods(self, tmp_path: Path):
        """Test discovering connector by characteristic methods."""
        connector_code = '''
class CustomConnector:
    """Custom connector with get_data and transform."""

    def get_data(self):
        return []

    def transform(self, data):
        return []
'''
        (tmp_path / "connector.py").write_text(connector_code)

        discovery = ProjectDiscovery(tmp_path)
        connectors = discovery.discover_connectors()

        assert len(connectors) == 1
        assert connectors[0].class_name == "CustomConnector"
        assert "get_data" in connectors[0].methods
        assert "transform" in connectors[0].methods

    def test_discover_connectors_skips_test_files(self, tmp_path: Path):
        """Test that test files are skipped."""
        connector_code = '''
class TestConnector:
    def get_data(self):
        return []
'''
        (tmp_path / "test_connector.py").write_text(connector_code)

        discovery = ProjectDiscovery(tmp_path)
        connectors = discovery.discover_connectors()

        assert len(connectors) == 0

    def test_discover_connectors_skips_private_files(self, tmp_path: Path):
        """Test that private files are skipped."""
        connector_code = '''
class PrivateConnector:
    def get_data(self):
        return []
'''
        (tmp_path / "_private.py").write_text(connector_code)

        discovery = ProjectDiscovery(tmp_path)
        connectors = discovery.discover_connectors()

        assert len(connectors) == 0

    def test_discover_connectors_in_src_directory(self, tmp_path: Path):
        """Test discovering connectors in src directory."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        connector_code = '''
class SrcConnector:
    def get_data(self):
        return []

    def transform(self, data):
        return []
'''
        (src_dir / "connector.py").write_text(connector_code)

        discovery = ProjectDiscovery(tmp_path)
        connectors = discovery.discover_connectors()

        assert len(connectors) == 1
        assert connectors[0].class_name == "SrcConnector"

    def test_discover_connectors_with_type_parameter(self, tmp_path: Path):
        """Test extracting type parameter from generic base."""
        connector_code = '''
from typing import TypedDict

class DocData(TypedDict):
    id: str
    title: str

class TypedConnector(BaseDatasourceConnector[DocData]):
    def get_data(self):
        return []

    def transform(self, data):
        return []
'''
        (tmp_path / "connector.py").write_text(connector_code)

        discovery = ProjectDiscovery(tmp_path)
        connectors = discovery.discover_connectors()

        assert len(connectors) == 1
        assert connectors[0].source_type == "DocData"

    def test_discover_connectors_multiple(self, tmp_path: Path):
        """Test discovering multiple connectors."""
        connector_code = '''
class ConnectorA:
    def get_data(self):
        return []

    def transform(self, data):
        return []


class ConnectorB:
    def get_data(self):
        return []

    def transform(self, data):
        return []


class NotAConnector:
    def other_method(self):
        pass
'''
        (tmp_path / "connectors.py").write_text(connector_code)

        discovery = ProjectDiscovery(tmp_path)
        connectors = discovery.discover_connectors()

        assert len(connectors) == 2
        names = {c.class_name for c in connectors}
        assert names == {"ConnectorA", "ConnectorB"}

    def test_discover_connectors_syntax_error_handled(self, tmp_path: Path):
        """Test that syntax errors in files are handled gracefully."""
        (tmp_path / "broken.py").write_text("def broken(:\n    pass")
        (tmp_path / "good.py").write_text('''
class GoodConnector:
    def get_data(self):
        return []

    def transform(self, data):
        return []
''')

        discovery = ProjectDiscovery(tmp_path)
        connectors = discovery.discover_connectors()

        # Should still find the good connector
        assert len(connectors) == 1
        assert connectors[0].class_name == "GoodConnector"


class TestConnectorInfo:
    """Tests for ConnectorInfo dataclass."""

    def test_connector_info_fields(self):
        """Test ConnectorInfo has expected fields."""
        info = ConnectorInfo(
            class_name="TestConnector",
            module_path="src.connector",
            file_path="/path/to/connector.py",
            source_type="DocData",
            base_classes=["BaseDatasourceConnector"],
            methods=["get_data", "transform"],
            docstring="A connector",
        )

        assert info.class_name == "TestConnector"
        assert info.module_path == "src.connector"
        assert info.file_path == "/path/to/connector.py"
        assert info.source_type == "DocData"
        assert info.base_classes == ["BaseDatasourceConnector"]
        assert info.methods == ["get_data", "transform"]
        assert info.docstring == "A connector"


class TestProjectInfo:
    """Tests for ProjectInfo dataclass."""

    def test_project_info_fields(self):
        """Test ProjectInfo has expected fields."""
        info = ProjectInfo(
            path="/path/to/project",
            name="my-project",
            python_version="3.10.0",
            has_pyproject=True,
            has_mock_data=True,
            mock_data_path="/path/to/mock_data.json",
        )

        assert info.path == "/path/to/project"
        assert info.name == "my-project"
        assert info.python_version == "3.10.0"
        assert info.has_pyproject is True
        assert info.has_mock_data is True
        assert info.mock_data_path == "/path/to/mock_data.json"
