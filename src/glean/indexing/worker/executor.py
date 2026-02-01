"""Connector execution with event emission for the worker module.

Executes connectors and emits events as JSON-RPC notifications.
"""

import asyncio
import json
import logging
import sys
import time
import traceback
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from glean.indexing.worker.discovery import ConnectorInfo, ProjectDiscovery
from glean.indexing.worker.protocol import (
    ExecutionCompleteNotification,
    JsonRpcNotification,
    LogNotification,
    PhaseCompleteNotification,
    PhaseStartNotification,
    RecordFetchedNotification,
    TransformCompleteNotification,
    TransformErrorNotification,
)

logger = logging.getLogger(__name__)


class ExecutionState(str, Enum):
    """Execution state machine states."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"
    ERROR = "error"


@dataclass
class ExecutionConfig:
    """Configuration for connector execution."""

    step_mode: bool = False
    mock_data_path: Optional[str] = None


class ConnectorExecutor:
    """Executes a connector and emits events."""

    def __init__(
        self,
        project_path: Path,
        emit_notification: Callable[[JsonRpcNotification], None],
    ) -> None:
        self.project_path = project_path
        self.emit_notification = emit_notification
        self.discovery = ProjectDiscovery(project_path)

        self.execution_id: Optional[str] = None
        self.state = ExecutionState.PENDING
        self.connector_info: Optional[ConnectorInfo] = None
        self.connector_instance: Any = None

        # Execution stats
        self.total_records = 0
        self.successful_records = 0
        self.failed_records = 0
        self.start_time: Optional[float] = None

        # Control events
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Start unpaused
        self._abort_requested = False
        self._step_mode = False
        self._step_event = asyncio.Event()

    def emit(self, notification: JsonRpcNotification) -> None:
        """Emit a notification to the parent process."""
        self.emit_notification(notification)

    def log(self, level: str, message: str) -> None:
        """Emit a log notification."""
        source = self.connector_info.class_name if self.connector_info else None
        self.emit(LogNotification(level=level, message=message, source=source).to_notification())

    async def execute(
        self,
        connector_name: str,
        config: ExecutionConfig,
    ) -> None:
        """Execute a connector with the given configuration."""
        self.execution_id = str(uuid.uuid4())
        self.state = ExecutionState.RUNNING
        self.start_time = time.time()
        self._step_mode = config.step_mode

        if not self._step_mode:
            self._step_event.set()

        try:
            # Find the connector
            connectors = self.discovery.discover_connectors()
            matching = [c for c in connectors if c.class_name == connector_name]

            if not matching:
                raise ValueError(f"Connector '{connector_name}' not found in project")

            self.connector_info = matching[0]
            self.log("info", f"Found connector: {self.connector_info.class_name}")

            # Load connector class
            connector_class = self.discovery.load_connector_class(self.connector_info)
            self.log("info", f"Loaded connector class: {connector_class}")

            # Load mock data if specified
            mock_data = self._load_mock_data(config.mock_data_path)
            if mock_data:
                self.total_records = len(mock_data)
                self.log("info", f"Loaded {self.total_records} mock records")
                use_real_data = False
            else:
                # No mock data - try to use real data client
                self.log("info", "No mock data found, attempting to use real data client")
                use_real_data = True

            # Collect fetched records for transformation
            fetched_records: List[Dict[str, Any]] = []

            if use_real_data:
                # Try to fetch real data from the data client
                fetched_records = await self._run_real_fetch_phase(connector_class)
                if not fetched_records:
                    self.log("warning", "No records fetched from data client")
            else:
                # Phase 1: Fetch data (mock mode)
                await self._run_fetch_phase(mock_data)
                fetched_records = mock_data

            if self._abort_requested:
                self.state = ExecutionState.ABORTED
                return

            # Phase 2: Transform data
            await self._run_transform_phase(connector_class, fetched_records)

            if self._abort_requested:
                self.state = ExecutionState.ABORTED
                return

            # Phase 3: Upload (mock)
            await self._run_upload_phase()

            self.state = ExecutionState.COMPLETED

        except Exception as e:
            self.state = ExecutionState.ERROR
            self.log("error", f"Execution error: {e}")
            logger.exception("Execution error")
            raise

        finally:
            # Emit completion
            total_duration = (time.time() - (self.start_time or time.time())) * 1000
            self.emit(
                ExecutionCompleteNotification(
                    execution_id=self.execution_id or "",
                    success=self.state == ExecutionState.COMPLETED,
                    total_records=self.total_records,
                    successful_records=self.successful_records,
                    failed_records=self.failed_records,
                    total_duration_ms=total_duration,
                ).to_notification()
            )

    def _load_mock_data(self, mock_data_path: Optional[str]) -> List[Dict[str, Any]]:
        """Load mock data from a file."""
        if mock_data_path:
            path = Path(mock_data_path)
        else:
            # Try project discovery
            project_info = self.discovery.discover_project()
            if project_info.mock_data_path:
                path = Path(project_info.mock_data_path)
            else:
                # Try common locations
                for name in ["mock_data.json", "test_data.json"]:
                    candidate = self.project_path / name
                    if candidate.exists():
                        path = candidate
                        break
                else:
                    self.log("warning", "No mock data found")
                    return []

        try:
            with open(path) as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and "records" in data:
                    return data["records"]
                else:
                    return [data]
        except Exception as e:
            self.log("error", f"Failed to load mock data: {e}")
            return []

    async def _run_fetch_phase(self, mock_data: List[Dict[str, Any]]) -> None:
        """Run the data fetching phase."""
        phase_name = "get_data"
        phase_start = time.time()

        self.emit(
            PhaseStartNotification(
                phase=phase_name, total_records=len(mock_data)
            ).to_notification()
        )

        self.log("info", f"Starting {phase_name} phase with {len(mock_data)} records")

        for index, record in enumerate(mock_data):
            await self._wait_for_continue()
            if self._abort_requested:
                break

            record_id = str(record.get("id", f"record_{index}"))

            self.emit(
                RecordFetchedNotification(
                    record_id=record_id, index=index, data=record
                ).to_notification()
            )

            await self._step_pause()

        phase_duration = (time.time() - phase_start) * 1000
        self.emit(
            PhaseCompleteNotification(
                phase=phase_name,
                records_processed=len(mock_data),
                duration_ms=phase_duration,
            ).to_notification()
        )

    async def _run_real_fetch_phase(self, connector_class: Any) -> List[Dict[str, Any]]:
        """Run the data fetching phase using the real data client."""
        phase_name = "get_data"
        phase_start = time.time()
        fetched_records: List[Dict[str, Any]] = []

        # Emit phase start (unknown total records)
        self.emit(
            PhaseStartNotification(
                phase=phase_name, total_records=None
            ).to_notification()
        )

        self.log("info", f"Starting {phase_name} phase with real data client")

        try:
            # Find and instantiate the data client
            data_client = self._instantiate_data_client_for_connector(connector_class)

            if data_client is None:
                self.log("error", "Could not find or instantiate a data client for this connector")
                phase_duration = (time.time() - phase_start) * 1000
                self.emit(
                    PhaseCompleteNotification(
                        phase=phase_name,
                        records_processed=0,
                        duration_ms=phase_duration,
                        success=False,
                        error="No data client found",
                    ).to_notification()
                )
                return []

            self.log("info", f"Using data client: {type(data_client).__name__}")

            # Check if this is an async streaming data client
            if hasattr(data_client, "get_source_data"):
                index = 0
                get_source_data = data_client.get_source_data()

                # Check if it's an async generator
                if hasattr(get_source_data, "__anext__"):
                    async for record in get_source_data:
                        await self._wait_for_continue()
                        if self._abort_requested:
                            break

                        # Convert record to dict if needed
                        record_dict = self._record_to_dict(record)
                        record_id = str(record_dict.get("id", f"record_{index}"))

                        self.emit(
                            RecordFetchedNotification(
                                record_id=record_id, index=index, data=record_dict
                            ).to_notification()
                        )

                        fetched_records.append(record_dict)
                        index += 1
                        await self._step_pause()
                else:
                    # Sync generator
                    for record in get_source_data:
                        await self._wait_for_continue()
                        if self._abort_requested:
                            break

                        record_dict = self._record_to_dict(record)
                        record_id = str(record_dict.get("id", f"record_{index}"))

                        self.emit(
                            RecordFetchedNotification(
                                record_id=record_id, index=index, data=record_dict
                            ).to_notification()
                        )

                        fetched_records.append(record_dict)
                        index += 1
                        await self._step_pause()

                self.total_records = len(fetched_records)

        except Exception as e:
            self.log("error", f"Error fetching data: {e}")
            logger.exception("Error in real fetch phase")

        phase_duration = (time.time() - phase_start) * 1000
        self.emit(
            PhaseCompleteNotification(
                phase=phase_name,
                records_processed=len(fetched_records),
                duration_ms=phase_duration,
                success=len(fetched_records) > 0,
            ).to_notification()
        )

        return fetched_records

    def _record_to_dict(self, record: Any) -> Dict[str, Any]:
        """Convert a record (TypedDict, dataclass, Pydantic, etc.) to a plain dict."""
        if isinstance(record, dict):
            return record
        elif hasattr(record, "model_dump"):
            return record.model_dump()
        elif hasattr(record, "_asdict"):
            return record._asdict()
        elif hasattr(record, "__dict__"):
            return dict(record.__dict__)
        else:
            return {"data": record}

    def _instantiate_data_client_for_connector(self, connector_class: Any) -> Optional[Any]:
        """Try to find and instantiate the data client for a connector."""
        # Check if the connector has associated data clients
        if self.connector_info and self.connector_info.data_clients:
            for client_name in self.connector_info.data_clients:
                self.log("info", f"Found data client: {client_name}")
                try:
                    client_class = self._load_data_client_class(client_name)
                    if client_class:
                        instance = self._try_instantiate_data_client(client_class)
                        if instance is not None:
                            return instance
                except Exception as e:
                    self.log("debug", f"Could not load/instantiate {client_name}: {e}")

        # Fallback: scan all Python files for data client classes
        self.log("debug", "Falling back to scanning for data clients")
        return self._find_data_client_by_scan()

    def _load_data_client_class(self, class_name: str) -> Optional[Any]:
        """Load a data client class by name from the project."""
        import ast
        import importlib.util

        # Search for the class in Python files
        search_paths = [
            self.project_path,
            self.project_path / "src",
        ]

        for search_path in search_paths:
            if not search_path.exists():
                continue

            for py_file in search_path.rglob("*.py"):
                path_str = str(py_file)
                if any(skip in path_str for skip in ["__pycache__", ".venv", "venv", "node_modules"]):
                    continue

                try:
                    source = py_file.read_text()
                    tree = ast.parse(source)

                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef) and node.name == class_name:
                            # Found it - load the module
                            rel_path = py_file.relative_to(self.project_path)
                            module_path = str(rel_path.with_suffix("")).replace("/", ".")

                            if str(self.project_path) not in sys.path:
                                sys.path.insert(0, str(self.project_path))

                            spec = importlib.util.spec_from_file_location(module_path, py_file)
                            if spec and spec.loader:
                                module = importlib.util.module_from_spec(spec)
                                sys.modules[spec.name] = module
                                spec.loader.exec_module(module)
                                return getattr(module, class_name, None)
                except Exception as e:
                    self.log("debug", f"Error searching {py_file}: {e}")

        return None

    def _find_data_client_by_scan(self) -> Optional[Any]:
        """Scan project for any data client class."""
        import ast
        import importlib.util

        search_paths = [
            self.project_path,
            self.project_path / "src",
        ]

        for search_path in search_paths:
            if not search_path.exists():
                continue

            for py_file in search_path.rglob("*.py"):
                path_str = str(py_file)
                if any(skip in path_str for skip in ["__pycache__", ".venv", "venv", "node_modules"]):
                    continue

                try:
                    source = py_file.read_text()
                    tree = ast.parse(source)

                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            # Check if this looks like a data client
                            base_names = []
                            for base in node.bases:
                                if isinstance(base, ast.Name):
                                    base_names.append(base.id)
                                elif isinstance(base, ast.Subscript) and isinstance(base.value, ast.Name):
                                    base_names.append(base.value.id)
                                elif isinstance(base, ast.Attribute):
                                    base_names.append(base.attr)

                            if any("DataClient" in name for name in base_names):
                                self.log("info", f"Found data client class: {node.name}")

                                rel_path = py_file.relative_to(self.project_path)
                                module_path = str(rel_path.with_suffix("")).replace("/", ".")

                                if str(self.project_path) not in sys.path:
                                    sys.path.insert(0, str(self.project_path))

                                spec = importlib.util.spec_from_file_location(module_path, py_file)
                                if spec and spec.loader:
                                    module = importlib.util.module_from_spec(spec)
                                    sys.modules[spec.name] = module
                                    spec.loader.exec_module(module)
                                    client_class = getattr(module, node.name, None)
                                    if client_class:
                                        instance = self._try_instantiate_data_client(client_class)
                                        if instance:
                                            return instance
                except Exception as e:
                    self.log("debug", f"Error scanning {py_file}: {e}")

        return None

    def _try_instantiate_data_client(self, client_class: Any) -> Optional[Any]:
        """Try various strategies to instantiate a data client."""
        import inspect
        import os

        # Get constructor parameters
        try:
            sig = inspect.signature(client_class.__init__)
            params = list(sig.parameters.keys())
            params = [p for p in params if p != "self"]
        except (ValueError, TypeError):
            params = []

        # Strategy 1: No required params
        if not params:
            try:
                return client_class()
            except Exception:
                pass

        # Strategy 2: Try with common parameter patterns from environment
        kwargs = {}

        for param in params:
            param_lower = param.lower()

            # Try to get from environment variables
            env_key = param.upper()
            if env_key in os.environ:
                kwargs[param] = os.environ[env_key]
                continue

            # Try common patterns
            if "url" in param_lower or "base_url" in param_lower:
                # Check for common env vars
                for env_var in ["BASE_URL", "DEV_DOCS_BASE_URL", "API_URL", "SITE_URL"]:
                    if env_var in os.environ:
                        kwargs[param] = os.environ[env_var]
                        break
            elif "logger" in param_lower:
                kwargs[param] = None  # Optional loggers default to None

        # Try instantiation with collected kwargs
        if kwargs:
            try:
                return client_class(**kwargs)
            except Exception as e:
                self.log("debug", f"Could not instantiate with kwargs {kwargs}: {e}")

        # Strategy 3: Try with all optional params set to None
        try:
            kwargs = {p: None for p in params}
            return client_class(**kwargs)
        except Exception:
            pass

        return None

    async def _run_transform_phase(
        self, connector_class: Any, mock_data: List[Dict[str, Any]]
    ) -> None:
        """Run the transformation phase."""
        phase_name = "transform"
        phase_start = time.time()

        self.emit(
            PhaseStartNotification(
                phase=phase_name, total_records=len(mock_data)
            ).to_notification()
        )

        self.log("info", f"Starting {phase_name} phase")

        # Try to instantiate connector
        connector_instance = self._try_instantiate_connector(connector_class)

        for index, record in enumerate(mock_data):
            await self._wait_for_continue()
            if self._abort_requested:
                break

            record_id = str(record.get("id", f"record_{index}"))
            transform_start = time.time()

            try:
                # Try to use connector's transform method
                if connector_instance and hasattr(connector_instance, "transform"):
                    output = connector_instance.transform([record])
                    if output:
                        output_data = self._serialize_output(output[0])
                    else:
                        output_data = self._simulate_transform(record)
                else:
                    output_data = self._simulate_transform(record)

                transform_duration = (time.time() - transform_start) * 1000
                field_mappings = self._detect_field_mappings(record, output_data)

                self.emit(
                    TransformCompleteNotification(
                        record_id=record_id,
                        index=index,
                        input_data=record,
                        output_data=output_data,
                        field_mappings=field_mappings,
                        duration_ms=transform_duration,
                    ).to_notification()
                )

                self.successful_records += 1

            except Exception as e:
                self.failed_records += 1
                self.emit(
                    TransformErrorNotification(
                        record_id=record_id,
                        index=index,
                        input_data=record,
                        error=str(e),
                        error_type=type(e).__name__,
                        traceback=traceback.format_exc(),
                    ).to_notification()
                )

            await self._step_pause()

        phase_duration = (time.time() - phase_start) * 1000
        self.emit(
            PhaseCompleteNotification(
                phase=phase_name,
                records_processed=self.successful_records + self.failed_records,
                duration_ms=phase_duration,
                success=self.failed_records == 0,
            ).to_notification()
        )

    async def _run_upload_phase(self) -> None:
        """Run the upload phase (mock)."""
        phase_name = "post_to_index"
        phase_start = time.time()

        self.emit(
            PhaseStartNotification(
                phase=phase_name, total_records=self.successful_records
            ).to_notification()
        )

        self.log(
            "info",
            f"Simulating upload of {self.successful_records} records (mock mode)",
        )

        # Simulate brief delay
        await asyncio.sleep(0.1)

        phase_duration = (time.time() - phase_start) * 1000
        self.emit(
            PhaseCompleteNotification(
                phase=phase_name,
                records_processed=self.successful_records,
                duration_ms=phase_duration,
            ).to_notification()
        )

    def _serialize_output(self, output: Any) -> Dict[str, Any]:
        """Serialize connector output to a dict."""
        if hasattr(output, "model_dump"):
            return output.model_dump()
        elif hasattr(output, "__dict__"):
            return output.__dict__
        elif isinstance(output, dict):
            return output
        else:
            return {"result": output}

    def _simulate_transform(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate transformation when no connector transform is available."""
        return {
            "id": input_data.get("id", str(uuid.uuid4())),
            "title": input_data.get("title", input_data.get("name", "Untitled")),
            "body": input_data.get("body", input_data.get("content", "")),
            "url": input_data.get("url", ""),
            "metadata": {
                k: v
                for k, v in input_data.items()
                if k not in ["id", "title", "body", "content", "name", "url"]
            },
        }

    def _try_instantiate_connector(self, connector_class: Any) -> Optional[Any]:
        """Try various strategies to instantiate a connector."""
        # Strategy 1: Try direct instantiation (for simple connectors)
        try:
            return connector_class()
        except TypeError:
            pass  # Needs arguments

        # Strategy 2: For streaming connectors, try to find and use data client
        # Look for a data_client class in the same module or discovered classes
        data_client = self._find_data_client_for_connector(connector_class)
        if data_client is not None:
            try:
                # Get datasource name from connector's configuration if available
                name = "studio_test"
                if hasattr(connector_class, "configuration"):
                    config = connector_class.configuration
                    if hasattr(config, "name"):
                        name = config.name

                return connector_class(name, data_client)
            except Exception as e:
                self.log("debug", f"Could not instantiate with data client: {e}")

        # Strategy 3: Create a mock data client wrapper
        try:
            name = "studio_test"
            if hasattr(connector_class, "configuration"):
                config = connector_class.configuration
                if hasattr(config, "name"):
                    name = config.name

            # Try with a mock data client that yields nothing
            mock_client = self._create_mock_data_client()
            if mock_client is not None:
                return connector_class(name, mock_client)
        except Exception as e:
            self.log("debug", f"Could not instantiate with mock client: {e}")

        self.log("info", "Using simulation mode for transformation")
        return None

    def _find_data_client_for_connector(self, connector_class: Any) -> Optional[Any]:
        """Try to find and instantiate a matching data client."""
        # Get all discovered connectors (which includes data clients)
        connectors = self.discovery.discover_connectors()

        # Look for classes with "DataClient" in the name or base classes
        for info in connectors:
            if "DataClient" in info.class_name or any(
                "DataClient" in bc for bc in info.base_classes
            ):
                try:
                    client_class = self.discovery.load_connector_class(info)
                    # Try to instantiate the data client
                    return client_class()
                except Exception as e:
                    self.log("debug", f"Could not instantiate {info.class_name}: {e}")

        return None

    def _create_mock_data_client(self) -> Optional[Any]:
        """Create a mock data client for testing."""
        # Create a simple mock that yields nothing
        # This allows us to at least test the transform method
        try:
            from glean.indexing.connectors import BaseStreamingDataClient

            class MockDataClient(BaseStreamingDataClient):
                def get_source_data(self, **kwargs):
                    return iter([])

            return MockDataClient()
        except ImportError:
            return None

    def _detect_field_mappings(
        self, input_data: Dict[str, Any], output_data: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """Detect which input fields mapped to which output fields."""
        mappings = []

        for out_key, out_value in output_data.items():
            if out_key == "metadata" and isinstance(out_value, dict):
                for meta_key, meta_value in out_value.items():
                    for in_key, in_value in input_data.items():
                        if in_value == meta_value and in_value is not None:
                            mappings.append(
                                {"source_field": in_key, "target_field": f"metadata.{meta_key}"}
                            )
            else:
                for in_key, in_value in input_data.items():
                    if in_value == out_value and in_value is not None:
                        mappings.append({"source_field": in_key, "target_field": out_key})

        return mappings

    async def _wait_for_continue(self) -> None:
        """Wait if execution is paused."""
        await self._pause_event.wait()

    async def _step_pause(self) -> None:
        """Pause after each step if in step mode."""
        if self._step_mode:
            self._step_event.clear()
            await self._step_event.wait()

    def pause(self) -> None:
        """Pause execution."""
        self._pause_event.clear()
        self.state = ExecutionState.PAUSED

    def resume(self) -> None:
        """Resume execution."""
        self._pause_event.set()
        if self.state == ExecutionState.PAUSED:
            self.state = ExecutionState.RUNNING

    def step(self) -> None:
        """Execute one step in step mode."""
        self._step_event.set()

    def abort(self) -> None:
        """Abort execution."""
        self._abort_requested = True
        self._pause_event.set()
        self._step_event.set()
