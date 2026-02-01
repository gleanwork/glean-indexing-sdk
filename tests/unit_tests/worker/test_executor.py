"""Tests for connector executor."""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from glean.indexing.worker.executor import (
    ConnectorExecutor,
    ExecutionConfig,
    ExecutionState,
)
from glean.indexing.worker.protocol import JsonRpcNotification


class TestExecutionState:
    """Tests for ExecutionState enum."""

    def test_states_exist(self):
        """Test that expected states exist."""
        assert ExecutionState.PENDING == "pending"
        assert ExecutionState.RUNNING == "running"
        assert ExecutionState.PAUSED == "paused"
        assert ExecutionState.COMPLETED == "completed"
        assert ExecutionState.ABORTED == "aborted"
        assert ExecutionState.ERROR == "error"


class TestExecutionConfig:
    """Tests for ExecutionConfig dataclass."""

    def test_default_values(self):
        """Test default config values."""
        config = ExecutionConfig()
        assert config.step_mode is False
        assert config.mock_data_path is None

    def test_custom_values(self):
        """Test custom config values."""
        config = ExecutionConfig(step_mode=True, mock_data_path="/path/to/data.json")
        assert config.step_mode is True
        assert config.mock_data_path == "/path/to/data.json"


class TestConnectorExecutor:
    """Tests for ConnectorExecutor class."""

    def create_executor(self, tmp_path: Path) -> ConnectorExecutor:
        """Create an executor for testing."""
        notifications = []

        def emit(notification: JsonRpcNotification):
            notifications.append(notification)

        executor = ConnectorExecutor(
            project_path=tmp_path,
            emit_notification=emit,
        )
        executor._notifications = notifications  # Store for assertions
        return executor

    def test_init(self, tmp_path: Path):
        """Test executor initialization."""
        executor = self.create_executor(tmp_path)
        assert executor.project_path == tmp_path
        assert executor.state == ExecutionState.PENDING
        assert executor.execution_id is None
        assert executor.total_records == 0
        assert executor.successful_records == 0
        assert executor.failed_records == 0

    def test_log_emits_notification(self, tmp_path: Path):
        """Test that log() emits a log notification."""
        executor = self.create_executor(tmp_path)
        executor.log("info", "Test message")

        assert len(executor._notifications) == 1
        notification = executor._notifications[0]
        assert notification.method == "log"
        assert notification.params["level"] == "info"
        assert notification.params["message"] == "Test message"

    def test_pause_resume(self, tmp_path: Path):
        """Test pause and resume functionality."""
        executor = self.create_executor(tmp_path)
        executor.state = ExecutionState.RUNNING

        # Initially not paused
        assert executor._pause_event.is_set()

        # Pause
        executor.pause()
        assert executor.state == ExecutionState.PAUSED
        assert not executor._pause_event.is_set()

        # Resume
        executor.resume()
        assert executor.state == ExecutionState.RUNNING
        assert executor._pause_event.is_set()

    def test_abort(self, tmp_path: Path):
        """Test abort functionality."""
        executor = self.create_executor(tmp_path)

        executor.abort()

        assert executor._abort_requested is True
        # Abort should also set pause/step events to unblock
        assert executor._pause_event.is_set()
        assert executor._step_event.is_set()

    def test_step(self, tmp_path: Path):
        """Test step functionality."""
        executor = self.create_executor(tmp_path)
        executor._step_mode = True
        executor._step_event.clear()

        executor.step()

        assert executor._step_event.is_set()

    def test_load_mock_data_from_path(self, tmp_path: Path):
        """Test loading mock data from specified path."""
        mock_data = [{"id": "1", "title": "Doc 1"}, {"id": "2", "title": "Doc 2"}]
        mock_file = tmp_path / "custom_mock.json"
        mock_file.write_text(json.dumps(mock_data))

        executor = self.create_executor(tmp_path)
        loaded = executor._load_mock_data(str(mock_file))

        assert len(loaded) == 2
        assert loaded[0]["id"] == "1"

    def test_load_mock_data_with_records_key(self, tmp_path: Path):
        """Test loading mock data with records key."""
        mock_data = {"records": [{"id": "1"}, {"id": "2"}], "meta": "ignored"}
        mock_file = tmp_path / "mock_data.json"
        mock_file.write_text(json.dumps(mock_data))

        executor = self.create_executor(tmp_path)
        loaded = executor._load_mock_data(str(mock_file))

        assert len(loaded) == 2

    def test_load_mock_data_single_object(self, tmp_path: Path):
        """Test loading single object as mock data."""
        mock_data = {"id": "single"}
        mock_file = tmp_path / "mock_data.json"
        mock_file.write_text(json.dumps(mock_data))

        executor = self.create_executor(tmp_path)
        loaded = executor._load_mock_data(str(mock_file))

        assert len(loaded) == 1
        assert loaded[0]["id"] == "single"

    def test_load_mock_data_auto_discover(self, tmp_path: Path):
        """Test auto-discovering mock_data.json."""
        mock_data = [{"id": "1"}]
        (tmp_path / "mock_data.json").write_text(json.dumps(mock_data))

        executor = self.create_executor(tmp_path)
        loaded = executor._load_mock_data(None)

        assert len(loaded) == 1

    def test_load_mock_data_not_found(self, tmp_path: Path):
        """Test handling missing mock data."""
        executor = self.create_executor(tmp_path)
        loaded = executor._load_mock_data(None)

        assert loaded == []

    def test_simulate_transform(self, tmp_path: Path):
        """Test simulated transformation."""
        executor = self.create_executor(tmp_path)
        input_data = {
            "id": "doc-1",
            "title": "Test Title",
            "body": "Test content",
            "url": "https://example.com",
            "author": "test@example.com",
        }

        output = executor._simulate_transform(input_data)

        assert output["id"] == "doc-1"
        assert output["title"] == "Test Title"
        assert output["body"] == "Test content"
        assert output["url"] == "https://example.com"
        assert "author" in output["metadata"]

    def test_detect_field_mappings(self, tmp_path: Path):
        """Test field mapping detection."""
        executor = self.create_executor(tmp_path)
        input_data = {"source_title": "Hello", "source_id": "123"}
        output_data = {"title": "Hello", "id": "123", "metadata": {"source_id": "123"}}

        mappings = executor._detect_field_mappings(input_data, output_data)

        # Should find mappings for title and id
        assert len(mappings) >= 2
        source_fields = {m["source_field"] for m in mappings}
        assert "source_title" in source_fields or "source_id" in source_fields

    @pytest.mark.asyncio
    async def test_run_fetch_phase(self, tmp_path: Path):
        """Test fetch phase execution."""
        executor = self.create_executor(tmp_path)
        executor.execution_id = "test-exec"
        mock_data = [{"id": "1"}, {"id": "2"}]

        await executor._run_fetch_phase(mock_data)

        # Should have emitted phase_start, record_fetched (x2), phase_complete
        methods = [n.method for n in executor._notifications]
        assert "phase_start" in methods
        assert methods.count("record_fetched") == 2
        assert "phase_complete" in methods

    @pytest.mark.asyncio
    async def test_run_fetch_phase_abort(self, tmp_path: Path):
        """Test fetch phase handles abort."""
        executor = self.create_executor(tmp_path)
        executor.execution_id = "test-exec"
        executor._abort_requested = True
        mock_data = [{"id": "1"}, {"id": "2"}, {"id": "3"}]

        await executor._run_fetch_phase(mock_data)

        # Should abort early, not fetch all records
        record_fetched_count = sum(
            1 for n in executor._notifications if n.method == "record_fetched"
        )
        assert record_fetched_count < 3

    @pytest.mark.asyncio
    async def test_run_transform_phase(self, tmp_path: Path):
        """Test transform phase execution."""
        executor = self.create_executor(tmp_path)
        executor.execution_id = "test-exec"
        mock_data = [{"id": "1", "title": "Test"}]

        # Use a mock connector class
        mock_connector_class = MagicMock()
        mock_connector_class.return_value = None  # Cannot instantiate

        await executor._run_transform_phase(mock_connector_class, mock_data)

        # Should have emitted phase_start, transform_complete, phase_complete
        methods = [n.method for n in executor._notifications]
        assert "phase_start" in methods
        assert "transform_complete" in methods
        assert "phase_complete" in methods
        assert executor.successful_records == 1

    @pytest.mark.asyncio
    async def test_run_upload_phase(self, tmp_path: Path):
        """Test upload phase execution."""
        executor = self.create_executor(tmp_path)
        executor.execution_id = "test-exec"
        executor.successful_records = 5

        await executor._run_upload_phase()

        methods = [n.method for n in executor._notifications]
        assert "phase_start" in methods
        assert "phase_complete" in methods

    @pytest.mark.asyncio
    async def test_execute_full_flow(self, tmp_path: Path):
        """Test full execution flow with mock data."""
        # Create mock data
        mock_data = [{"id": "1", "title": "Doc 1"}]
        (tmp_path / "mock_data.json").write_text(json.dumps(mock_data))

        # Create a simple connector file
        connector_code = '''
class TestConnector:
    def get_data(self):
        return []

    def transform(self, data):
        return data
'''
        (tmp_path / "connector.py").write_text(connector_code)

        executor = self.create_executor(tmp_path)
        config = ExecutionConfig()

        await executor.execute("TestConnector", config)

        # Check final state
        assert executor.state == ExecutionState.COMPLETED
        assert executor.execution_id is not None

        # Check execution_complete was emitted
        complete_notifications = [
            n for n in executor._notifications if n.method == "execution_complete"
        ]
        assert len(complete_notifications) == 1
        assert complete_notifications[0].params["success"] is True

    @pytest.mark.asyncio
    async def test_execute_connector_not_found(self, tmp_path: Path):
        """Test execution fails when connector not found."""
        executor = self.create_executor(tmp_path)
        config = ExecutionConfig()

        with pytest.raises(ValueError, match="not found"):
            await executor.execute("NonExistentConnector", config)

        assert executor.state == ExecutionState.ERROR
