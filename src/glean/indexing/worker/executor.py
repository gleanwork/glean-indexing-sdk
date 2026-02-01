"""Connector execution with event emission for the worker module.

Executes connectors and emits events as JSON-RPC notifications.
"""

import asyncio
import json
import logging
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

            # Phase 1: Fetch data
            await self._run_fetch_phase(mock_data)

            if self._abort_requested:
                self.state = ExecutionState.ABORTED
                return

            # Phase 2: Transform data
            await self._run_transform_phase(connector_class, mock_data)

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
        connector_instance = None
        try:
            connector_instance = connector_class()
        except Exception as e:
            self.log("warning", f"Could not instantiate connector: {e}")

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
