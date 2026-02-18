"""Project and connector discovery for the worker module.

Discovers connectors in the current project by analyzing Python files.
"""

import importlib.util
import inspect
import logging
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Import SDK base classes for issubclass checks
try:
    from glean.indexing.connectors import (
        BaseAsyncStreamingDatasourceConnector,
        BaseConnector,
        BaseDataClient,
        BaseDatasourceConnector,
        BasePeopleConnector,
        BaseStreamingDatasourceConnector,
    )

    CONNECTOR_BASE_CLASSES: tuple[type, ...] = (
        BaseConnector,
        BaseDatasourceConnector,
        BaseStreamingDatasourceConnector,
        BaseAsyncStreamingDatasourceConnector,
        BasePeopleConnector,
    )
    DATA_CLIENT_BASE_CLASSES: tuple[type, ...] = (BaseDataClient,)
except ImportError:
    CONNECTOR_BASE_CLASSES = ()
    DATA_CLIENT_BASE_CLASSES = ()


class ConnectorInfo(BaseModel):
    """Information about a discovered connector class."""

    class_name: str
    module_path: str
    file_path: str
    source_type: str | None = None
    base_classes: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    docstring: str | None = None
    category: str = "connector"
    data_clients: list[str] = Field(default_factory=list)
    configuration: dict | None = None


class ProjectInfo(BaseModel):
    """Information about the current project."""

    path: str
    name: str
    python_version: str
    has_pyproject: bool = False
    has_mock_data: bool = False
    mock_data_path: str | None = None


def _is_connector_subclass(cls: type) -> bool:
    """Check if a class is a subclass of any known connector base class."""
    if not CONNECTOR_BASE_CLASSES:
        return False
    try:
        return issubclass(cls, CONNECTOR_BASE_CLASSES) and cls not in CONNECTOR_BASE_CLASSES
    except TypeError:
        return False


def _is_data_client_subclass(cls: type) -> bool:
    """Check if a class is a subclass of any known data client base class."""
    if not DATA_CLIENT_BASE_CLASSES:
        return False
    try:
        return issubclass(cls, DATA_CLIENT_BASE_CLASSES) and cls not in DATA_CLIENT_BASE_CLASSES
    except TypeError:
        return False


def _is_connector_by_heuristic(cls: type) -> bool:
    """Fallback heuristic: check if a class looks like a connector by its methods."""
    connector_methods = {"get_data", "transform", "index_data", "post_to_index"}
    class_methods = {name for name, _ in inspect.getmembers(cls, predicate=inspect.isfunction)}
    return bool(class_methods & connector_methods)


def _is_data_client_by_heuristic(cls: type) -> bool:
    """Fallback heuristic: check if a class looks like a data client by its name."""
    return "DataClient" in cls.__name__


def _extract_type_parameter(cls: type) -> str | None:
    """Extract type parameter T from a generic base like BaseDatasourceConnector[T]."""
    orig_bases = getattr(cls, "__orig_bases__", None)
    if orig_bases:
        for base in orig_bases:
            args = getattr(base, "__args__", None)
            if args:
                # Return the name of the first type argument
                first_arg = args[0]
                if hasattr(first_arg, "__name__"):
                    return first_arg.__name__
                return str(first_arg)
    return None


def _extract_configuration(cls: type) -> dict | None:
    """Extract the datasource configuration from a connector's class attribute.

    Handles Pydantic models (model_dump), dataclasses (asdict), and plain dicts.
    Returns None if no configuration attribute is found or extraction fails.
    """
    import dataclasses as _dc

    config = getattr(cls, "configuration", None)
    if config is None or isinstance(config, type):
        return None

    if hasattr(config, "model_dump"):
        try:
            return config.model_dump(exclude_none=True)
        except Exception:
            logger.debug(f"Failed to serialize configuration for {cls.__name__}")
            return None

    if _dc.is_dataclass(config) and not isinstance(config, type):
        try:
            return _dc.asdict(config)
        except Exception:
            return None

    if isinstance(config, dict):
        return config

    return None


def _extract_connector_info(cls: type, file_path: Path, project_path: Path) -> ConnectorInfo:
    """Extract connector information from a class using inspect."""
    # Base class names
    base_classes = [base.__name__ for base in cls.__bases__]

    # Public methods (non-underscore)
    methods = [
        name
        for name, _ in inspect.getmembers(cls, predicate=inspect.isfunction)
        if not name.startswith("_")
    ]

    # Type parameter from generic bases
    source_type = _extract_type_parameter(cls)

    # Calculate module path relative to project
    rel_path = file_path.relative_to(project_path)
    module_path = str(rel_path.with_suffix("")).replace("/", ".")

    return ConnectorInfo(
        class_name=cls.__name__,
        module_path=module_path,
        file_path=str(file_path),
        source_type=source_type,
        base_classes=base_classes,
        methods=methods,
        docstring=inspect.getdoc(cls),
        configuration=_extract_configuration(cls),
    )


class ProjectDiscovery:
    """Discovers project metadata and connectors."""

    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path.resolve()

    def discover_project(self) -> ProjectInfo:
        """Discover project metadata."""
        name = self.project_path.name
        python_version = (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        )

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

    def discover_connectors(self) -> list[ConnectorInfo]:
        """Discover connector classes in the project.

        Returns connectors with their associated data clients linked via source_type matching.
        Data clients are included in each connector's `data_clients` list.
        """
        all_classes: list[ConnectorInfo] = []
        seen: set[tuple[str, str]] = set()  # (file_path, class_name)

        # Ensure project paths are on sys.path for imports
        if str(self.project_path) not in sys.path:
            sys.path.insert(0, str(self.project_path))

        src_path = self.project_path / "src"
        if src_path.exists() and str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))

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
                    found = self._import_and_scan_file(py_file)
                    for connector in found:
                        key = (connector.file_path, connector.class_name)
                        if key not in seen:
                            seen.add(key)
                            all_classes.append(connector)
                except Exception as e:
                    logger.debug(f"Error scanning {py_file}: {e}")

        # Categorize and link: match connectors with data clients by source_type
        return self._categorize_and_link(all_classes)

    def _import_and_scan_file(self, file_path: Path) -> list[ConnectorInfo]:
        """Import a Python file and scan for connector/data-client classes."""
        connectors: list[ConnectorInfo] = []

        # Build a unique module name to avoid collisions
        rel_path = file_path.relative_to(self.project_path)
        module_name = f"_discovery_.{str(rel_path.with_suffix('')).replace('/', '.')}"

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return []

        module = importlib.util.module_from_spec(spec)

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.debug(f"Could not import {file_path}: {e}")
            return []

        # Scan all classes defined in this module
        for _name, cls in inspect.getmembers(module, inspect.isclass):
            # Only consider classes actually defined in this file
            if getattr(cls, "__module__", None) != module_name:
                continue

            # Try issubclass checks first (when SDK base classes are available)
            is_connector = _is_connector_subclass(cls)
            is_data_client = _is_data_client_subclass(cls)

            # Fall back to heuristics for classes that don't subclass SDK bases
            if not is_connector and not is_data_client:
                is_data_client = _is_data_client_by_heuristic(cls)
                if not is_data_client:
                    is_connector = _is_connector_by_heuristic(cls)

            if is_connector or is_data_client:
                info = _extract_connector_info(cls, file_path, self.project_path)
                connectors.append(info)

        return connectors

    def _categorize_and_link(self, all_classes: list[ConnectorInfo]) -> list[ConnectorInfo]:
        """Categorize classes and link connectors to their data clients."""
        connectors: list[ConnectorInfo] = []
        data_clients: list[ConnectorInfo] = []

        # Categorize based on base classes
        for info in all_classes:
            is_data_client = any("DataClient" in bc for bc in info.base_classes)
            is_connector = (
                any("Connector" in bc or "DataSource" in bc for bc in info.base_classes)
                and not is_data_client
            )

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
        source_type_to_clients: dict[str, list[str]] = {}
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
        spec = importlib.util.spec_from_file_location(connector_info.module_path, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create module spec for {file_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        # Get the class
        connector_class = getattr(module, connector_info.class_name, None)
        if connector_class is None:
            raise ImportError(f"Class {connector_info.class_name} not found in {file_path}")

        return connector_class
