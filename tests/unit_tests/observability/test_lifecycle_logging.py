"""Tests for lifecycle logging and structured events in ConnectorObservability."""

import json
import logging
import uuid
from io import StringIO

import pytest

from glean.indexing.observability import ConnectorObservability, StructuredFormatter


class TestConnectorObservabilityInitialization:
    """Tests for ConnectorObservability initialization and field management."""

    def test_init_with_defaults(self):
        """Test initialization with minimal parameters."""
        obs = ConnectorObservability("test_connector")

        assert obs.connector_name == "test_connector"
        assert obs.datasource == "test_connector"
        assert obs.crawl_mode is None
        assert obs.run_id is not None
        assert isinstance(uuid.UUID(obs.run_id), uuid.UUID)

    def test_init_with_all_parameters(self):
        """Test initialization with all parameters provided."""
        test_run_id = str(uuid.uuid4())
        obs = ConnectorObservability(
            connector_name="my_connector",
            datasource="my_datasource",
            crawl_mode="full",
            run_id=test_run_id,
        )

        assert obs.connector_name == "my_connector"
        assert obs.datasource == "my_datasource"
        assert obs.crawl_mode == "full"
        assert obs.run_id == test_run_id

    def test_run_id_auto_generation(self):
        """Test that run_id is auto-generated when not provided."""
        obs1 = ConnectorObservability("connector1")
        obs2 = ConnectorObservability("connector2")

        assert obs1.run_id != obs2.run_id
        assert isinstance(uuid.UUID(obs1.run_id), uuid.UUID)
        assert isinstance(uuid.UUID(obs2.run_id), uuid.UUID)

    def test_crawl_mode_can_be_updated(self):
        """Test that crawl_mode can be set after initialization."""
        obs = ConnectorObservability("test_connector")
        assert obs.crawl_mode is None

        obs.crawl_mode = "incremental"
        assert obs.crawl_mode == "incremental"


class TestCommonFields:
    """Tests for get_common_fields method."""

    def test_get_common_fields_basic(self):
        """Test basic common fields without operation."""
        obs = ConnectorObservability(
            connector_name="test_connector",
            datasource="test_datasource",
            crawl_mode="full",
            run_id="test-run-123",
        )

        fields = obs.get_common_fields()

        assert fields == {
            "connector": "test_connector",
            "datasource": "test_datasource",
            "crawl_mode": "full",
            "run_id": "test-run-123",
        }

    def test_get_common_fields_with_operation(self):
        """Test common fields with operation parameter."""
        obs = ConnectorObservability("test_connector", run_id="test-run-123")
        fields = obs.get_common_fields(operation="batch_upload_started")

        assert fields["operation"] == "batch_upload_started"
        assert "connector" in fields
        assert "run_id" in fields

    def test_get_common_fields_without_crawl_mode(self):
        """Test that crawl_mode is omitted when None."""
        obs = ConnectorObservability("test_connector", crawl_mode=None)
        fields = obs.get_common_fields()

        assert "crawl_mode" not in fields
        assert "connector" in fields

    def test_get_common_fields_with_extra_kwargs(self):
        """Test that additional kwargs are included in common fields."""
        obs = ConnectorObservability("test_connector")
        fields = obs.get_common_fields(batch_index=5, item_count=100)

        assert fields["batch_index"] == 5
        assert fields["item_count"] == 100


class TestLifecycleEvents:
    """Tests for lifecycle event logging methods."""

    @pytest.fixture
    def observability_with_logger(self):
        """Create observability instance with captured logger output."""
        obs = ConnectorObservability(
            connector_name="test_connector",
            datasource="test_datasource",
            crawl_mode="full",
            run_id="test-run-123",
        )

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())

        logger = logging.getLogger("glean.indexing.observability.observability")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        yield obs, stream, logger

        logger.removeHandler(handler)

    def test_start_execution_emits_event(self, observability_with_logger):
        """Test that start_execution emits crawl_started event."""
        obs, stream, logger = observability_with_logger

        obs.start_execution()

        stream.seek(0)
        output = stream.read()
        log_data = json.loads(output)

        assert log_data["message"] == "Crawl started"
        assert log_data["operation"] == "crawl_started"
        assert log_data["connector"] == "test_connector"
        assert log_data["datasource"] == "test_datasource"
        assert log_data["crawl_mode"] == "full"
        assert log_data["run_id"] == "test-run-123"
        assert "timestamp" in log_data

    def test_end_execution_emits_event(self, observability_with_logger):
        """Test that end_execution emits crawl_completed event."""
        obs, stream, logger = observability_with_logger

        obs.start_execution()
        stream.truncate(0)
        stream.seek(0)

        obs.end_execution()

        stream.seek(0)
        output = stream.read()
        log_data = json.loads(output)

        assert log_data["message"] == "Crawl completed successfully"
        assert log_data["operation"] == "crawl_completed"
        assert log_data["status"] == "success"
        assert "duration_ms" in log_data
        assert log_data["duration_ms"] >= 0

    def test_fail_execution_emits_event(self, observability_with_logger):
        """Test that fail_execution emits crawl_failed event."""
        obs, stream, logger = observability_with_logger

        test_error = ValueError("Test error message")
        obs.start_execution()
        stream.truncate(0)
        stream.seek(0)

        obs.fail_execution(test_error)

        stream.seek(0)
        output = stream.read()
        log_data = json.loads(output)

        assert "Crawl failed" in log_data["message"]
        assert log_data["operation"] == "crawl_failed"
        assert log_data["status"] == "failed"
        assert log_data["error_type"] == "ValueError"
        assert log_data["error_message"] == "Test error message"
        assert log_data["level"] == "ERROR"

    def test_log_data_fetch_started(self, observability_with_logger):
        """Test data_fetch_started event logging."""
        obs, stream, logger = observability_with_logger

        obs.log_data_fetch_started(since="2024-01-01")

        stream.seek(0)
        log_data = json.loads(stream.read())

        assert log_data["message"] == "Data fetch started"
        assert log_data["operation"] == "data_fetch_started"
        assert log_data["since"] == "2024-01-01"

    def test_log_data_fetch_completed(self, observability_with_logger):
        """Test data_fetch_completed event logging."""
        obs, stream, logger = observability_with_logger

        obs.log_data_fetch_completed(item_count=150, duration_ms=2500)

        stream.seek(0)
        log_data = json.loads(stream.read())

        assert "150 items" in log_data["message"]
        assert log_data["operation"] == "data_fetch_completed"
        assert log_data["item_count"] == 150
        assert log_data["duration_ms"] == 2500
        assert log_data["status"] == "success"

    def test_log_transform_started(self, observability_with_logger):
        """Test transform_started event logging."""
        obs, stream, logger = observability_with_logger

        obs.log_transform_started(item_count=100)

        stream.seek(0)
        log_data = json.loads(stream.read())

        assert "100 items" in log_data["message"]
        assert log_data["operation"] == "transform_started"
        assert log_data["item_count"] == 100

    def test_log_transform_completed(self, observability_with_logger):
        """Test transform_completed event logging."""
        obs, stream, logger = observability_with_logger

        obs.log_transform_completed(input_count=100, output_count=95, duration_ms=1500)

        stream.seek(0)
        log_data = json.loads(stream.read())

        assert "100 → 95 items" in log_data["message"]
        assert log_data["operation"] == "transform_completed"
        assert log_data["input_count"] == 100
        assert log_data["output_count"] == 95
        assert log_data["duration_ms"] == 1500
        assert log_data["status"] == "success"

    def test_log_batch_upload_started(self, observability_with_logger):
        """Test batch_upload_started event logging."""
        obs, stream, logger = observability_with_logger

        obs.log_batch_upload_started(
            batch_index=2,
            batch_count=10,
            batch_size=50,
            entity_type="document",
        )

        stream.seek(0)
        log_data = json.loads(stream.read())

        assert "3/10" in log_data["message"]
        assert "50 documents" in log_data["message"]
        assert log_data["operation"] == "batch_upload_started"
        assert log_data["batch_index"] == 2
        assert log_data["batch_count"] == 10
        assert log_data["batch_size"] == 50
        assert log_data["entity_type"] == "document"

    def test_log_batch_upload_completed(self, observability_with_logger):
        """Test batch_upload_completed event logging."""
        obs, stream, logger = observability_with_logger

        obs.log_batch_upload_completed(
            batch_index=0,
            batch_count=5,
            batch_size=100,
            duration_ms=3000,
            entity_type="user",
        )

        stream.seek(0)
        log_data = json.loads(stream.read())

        assert "1/5" in log_data["message"]
        assert "100 users" in log_data["message"]
        assert log_data["operation"] == "batch_upload_completed"
        assert log_data["duration_ms"] == 3000
        assert log_data["entity_type"] == "user"
        assert log_data["status"] == "success"

    def test_log_batch_upload_failed(self, observability_with_logger):
        """Test batch_upload_failed event logging."""
        obs, stream, logger = observability_with_logger

        test_error = ConnectionError("Network timeout")
        obs.log_batch_upload_failed(
            batch_index=1,
            batch_count=3,
            error=test_error,
            entity_type="document",
        )

        stream.seek(0)
        log_data = json.loads(stream.read())

        assert "2/3" in log_data["message"]
        assert log_data["operation"] == "batch_upload_failed"
        assert log_data["status"] == "failed"
        assert log_data["error_type"] == "ConnectionError"
        assert log_data["error_message"] == "Network timeout"
        assert log_data["level"] == "ERROR"


class TestBackwardCompatibility:
    """Tests ensuring backward compatibility with existing behavior."""

    def test_basic_usage_without_structured_logging(self):
        """Test that basic observability works without structured logging."""
        obs = ConnectorObservability("test_connector")

        obs.start_execution()
        obs.record_metric("test_metric", 123)
        obs.increment_counter("test_counter")
        obs.start_timer("operation")
        obs.end_timer("operation")
        obs.end_execution()

        summary = obs.get_metrics_summary()
        assert summary["test_metric"] == 123
        assert summary["test_counter"] == 1
        assert "operation_duration" in summary
        assert "total_execution_time" in summary

    def test_existing_methods_unchanged(self):
        """Test that existing public methods maintain their signatures."""
        obs = ConnectorObservability("test_connector")

        assert hasattr(obs, "start_execution")
        assert hasattr(obs, "end_execution")
        assert hasattr(obs, "record_metric")
        assert hasattr(obs, "increment_counter")
        assert hasattr(obs, "start_timer")
        assert hasattr(obs, "end_timer")
        assert hasattr(obs, "get_metrics_summary")

        obs.start_execution()
        obs.record_metric("key", 100)
        obs.increment_counter("counter", 5)
        obs.end_execution()

        summary = obs.get_metrics_summary()
        assert summary["key"] == 100
        assert summary["counter"] == 5


class TestIntegrationWithStructuredFormatter:
    """Integration tests with StructuredFormatter."""

    def test_lifecycle_events_with_structured_formatter(self):
        """Test that all lifecycle events work correctly with StructuredFormatter."""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())

        logger = logging.getLogger("glean.indexing.observability.observability")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        try:
            obs = ConnectorObservability(
                connector_name="integration_test",
                datasource="test_datasource",
                crawl_mode="full",
            )

            obs.start_execution()
            obs.log_data_fetch_started()
            obs.log_data_fetch_completed(item_count=50, duration_ms=1000)
            obs.log_transform_started(item_count=50)
            obs.log_transform_completed(input_count=50, output_count=48, duration_ms=500)
            obs.log_batch_upload_started(batch_index=0, batch_count=1, batch_size=48)
            obs.log_batch_upload_completed(
                batch_index=0,
                batch_count=1,
                batch_size=48,
                duration_ms=2000,
            )
            obs.end_execution()

            stream.seek(0)
            log_lines = stream.read().strip().split("\n")

            assert len(log_lines) == 8

            for line in log_lines:
                log_data = json.loads(line)
                assert "run_id" in log_data
                assert log_data["run_id"] == obs.run_id

        finally:
            logger.removeHandler(handler)

    def test_all_events_include_common_fields(self):
        """Verify all lifecycle events include common correlation fields."""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())

        logger = logging.getLogger("glean.indexing.observability.observability")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        try:
            obs = ConnectorObservability(
                connector_name="field_test",
                datasource="test_ds",
                crawl_mode="incremental",
                run_id="fixed-run-id-123",
            )

            obs.start_execution()
            obs.log_data_fetch_completed(item_count=10, duration_ms=100)
            obs.log_batch_upload_started(batch_index=0, batch_count=1, batch_size=10)
            obs.end_execution()

            stream.seek(0)
            log_lines = stream.read().strip().split("\n")

            required_fields = {"connector", "datasource", "run_id", "crawl_mode"}
            for line in log_lines:
                log_data = json.loads(line)
                assert required_fields.issubset(log_data.keys())
                assert log_data["connector"] == "field_test"
                assert log_data["datasource"] == "test_ds"
                assert log_data["crawl_mode"] == "incremental"
                assert log_data["run_id"] == "fixed-run-id-123"

        finally:
            logger.removeHandler(handler)
