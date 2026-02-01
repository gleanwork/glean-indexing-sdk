"""Project and connector discovery for the worker module.

Discovers connectors in the current project by analyzing Python files.
"""

import ast
import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConnectorInfo:
    """Information about a discovered connector class."""

    class_name: str
    module_path: str
    file_path: str
    source_type: Optional[str] = None
    base_classes: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=list)
    docstring: Optional[str] = None
    # Category: "connector" or "data_client"
    category: str = "connector"
    # For connectors: list of data client class names that match by source_type
    data_clients: List[str] = field(default_factory=list)


@dataclass
class ProjectInfo:
    """Information about the current project."""

    path: str
    name: str
    python_version: str
    has_pyproject: bool = False
    has_mock_data: bool = False
    mock_data_path: Optional[str] = None


class ProjectDiscovery:
    """Discovers project metadata and connectors."""

    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path.resolve()

    def discover_project(self) -> ProjectInfo:
        """Discover project metadata."""
        name = self.project_path.name
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

        has_pyproject = (self.project_path / "pyproject.toml").exists()

        # Check for mock data
        mock_data_path = None
        has_mock_data = False
        for mock_file in ["mock_data.json", "test_data.json", ".mock_data.json"]:
            candidate = self.project_path / mock_file
            if candidate.exists():
                has_mock_data = True
                mock_data_path = str(candidate)
                break

        return ProjectInfo(
            path=str(self.project_path),
            name=name,
            python_version=python_version,
            has_pyproject=has_pyproject,
            has_mock_data=has_mock_data,
            mock_data_path=mock_data_path,
        )

    def discover_connectors(self) -> List[ConnectorInfo]:
        """Discover connector classes in the project.

        Returns connectors with their associated data clients linked via source_type matching.
        Data clients are included in each connector's `data_clients` list.
        """
        all_classes: List[ConnectorInfo] = []
        seen: set[tuple[str, str]] = set()  # (file_path, class_name)

        # Search common locations for connector files
        search_paths = [
            self.project_path,
            self.project_path / "src",
            self.project_path / "connectors",
        ]

        for search_path in search_paths:
            if not search_path.exists():
                continue

            for py_file in search_path.rglob("*.py"):
                # Skip test files, __pycache__, virtual envs, etc.
                path_str = str(py_file)
                if (
                    "__pycache__" in path_str
                    or ".venv" in path_str
                    or "venv" in path_str
                    or "node_modules" in path_str
                    or "site-packages" in path_str
                    or ".git" in path_str
                    or "test" in py_file.name.lower()
                    or py_file.name.startswith("_")
                ):
                    continue

                try:
                    found = self._parse_file_for_connectors(py_file)
                    for connector in found:
                        key = (connector.file_path, connector.class_name)
                        if key not in seen:
                            seen.add(key)
                            all_classes.append(connector)
                except Exception as e:
                    logger.debug(f"Error parsing {py_file}: {e}")

        # Categorize and link: match connectors with data clients by source_type
        return self._categorize_and_link(all_classes)

    def _categorize_and_link(self, all_classes: List[ConnectorInfo]) -> List[ConnectorInfo]:
        """Categorize classes and link connectors to their data clients."""
        connectors: List[ConnectorInfo] = []
        data_clients: List[ConnectorInfo] = []

        # Categorize based on base classes
        for info in all_classes:
            is_data_client = any(
                "DataClient" in bc for bc in info.base_classes
            )
            is_connector = any(
                "Connector" in bc or "DataSource" in bc
                for bc in info.base_classes
            ) and not is_data_client

            if is_data_client:
                info.category = "data_client"
                data_clients.append(info)
            elif is_connector:
                info.category = "connector"
                connectors.append(info)
            else:
                # Default to connector if has connector methods
                info.category = "connector"
                connectors.append(info)

        # Build a map of source_type -> data_client class names
        source_type_to_clients: dict[str, List[str]] = {}
        for dc in data_clients:
            if dc.source_type:
                if dc.source_type not in source_type_to_clients:
                    source_type_to_clients[dc.source_type] = []
                source_type_to_clients[dc.source_type].append(dc.class_name)

        # Link connectors to their data clients by matching source_type
        for conn in connectors:
            if conn.source_type and conn.source_type in source_type_to_clients:
                conn.data_clients = source_type_to_clients[conn.source_type]

        # Return only connectors (with data_clients embedded)
        # Data clients are not returned as top-level items
        return connectors

    def _parse_file_for_connectors(self, file_path: Path) -> List[ConnectorInfo]:
        """Parse a Python file for connector classes using AST."""
        connectors: List[ConnectorInfo] = []

        try:
            source = file_path.read_text()
            tree = ast.parse(source)
        except SyntaxError:
            return []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if self._is_connector_class(node):
                    info = self._extract_connector_info(node, file_path)
                    connectors.append(info)

        return connectors

    def _is_connector_class(self, node: ast.ClassDef) -> bool:
        """Check if a class definition appears to be a connector."""
        # Check base classes for connector indicators
        for base in node.bases:
            base_name = self._get_base_name(base)
            if any(
                indicator in base_name
                for indicator in ["Connector", "DataSource", "DataClient"]
            ):
                return True

        # Check for characteristic methods
        method_names = {
            n.name
            for n in node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        connector_methods = {"get_data", "transform", "index_data", "post_to_index"}
        return bool(method_names & connector_methods)

    def _get_base_name(self, node: ast.expr) -> str:
        """Extract the name from a base class node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name):
                return node.value.id
            elif isinstance(node.value, ast.Attribute):
                return node.value.attr
        elif isinstance(node, ast.Attribute):
            return node.attr
        return ""

    def _extract_connector_info(
        self, node: ast.ClassDef, file_path: Path
    ) -> ConnectorInfo:
        """Extract connector information from a class definition."""
        base_classes = [self._get_base_name(base) for base in node.bases]

        methods = [
            n.name
            for n in node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not n.name.startswith("_")
        ]

        source_type = self._extract_type_parameter(node)

        # Calculate module path relative to project
        rel_path = file_path.relative_to(self.project_path)
        module_path = str(rel_path.with_suffix("")).replace("/", ".")

        return ConnectorInfo(
            class_name=node.name,
            module_path=module_path,
            file_path=str(file_path),
            source_type=source_type,
            base_classes=base_classes,
            methods=methods,
            docstring=ast.get_docstring(node),
        )

    def _extract_type_parameter(self, node: ast.ClassDef) -> Optional[str]:
        """Extract type parameter T from BaseDatasourceConnector[T]."""
        for base in node.bases:
            if isinstance(base, ast.Subscript):
                return ast.unparse(base.slice)
        return None

    def load_connector_class(self, connector_info: ConnectorInfo) -> Any:
        """Load and return the actual connector class."""
        file_path = Path(connector_info.file_path)

        # Add project to path if needed
        if str(self.project_path) not in sys.path:
            sys.path.insert(0, str(self.project_path))

        src_path = self.project_path / "src"
        if src_path.exists() and str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))

        # Load the module
        spec = importlib.util.spec_from_file_location(
            connector_info.module_path, file_path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create module spec for {file_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        # Get the class
        connector_class = getattr(module, connector_info.class_name, None)
        if connector_class is None:
            raise ImportError(
                f"Class {connector_info.class_name} not found in {file_path}"
            )

        return connector_class
