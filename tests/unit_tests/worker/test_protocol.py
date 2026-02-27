"""Tests for JSON-RPC protocol types."""

from glean.indexing.worker.protocol import (
    ErrorCode,
    ExecutionCompleteNotification,
    HeartbeatNotification,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
    LogNotification,
    PhaseCompleteNotification,
    PhaseStartNotification,
    RecordFetchedNotification,
    TransformCompleteNotification,
    TransformErrorNotification,
)


class TestJsonRpcRequest:
    """Tests for JsonRpcRequest."""

    def test_model_validate_minimal(self):
        """Test parsing minimal request."""
        data = {"jsonrpc": "2.0", "method": "test", "id": 1}
        request = JsonRpcRequest.model_validate(data)
        assert request.method == "test"
        assert request.id == 1
        assert request.params is None

    def test_model_validate_with_params(self):
        """Test parsing request with params."""
        data = {
            "jsonrpc": "2.0",
            "method": "execute",
            "id": 42,
            "params": {"connector": "MyConnector"},
        }
        request = JsonRpcRequest.model_validate(data)
        assert request.method == "execute"
        assert request.id == 42
        assert request.params == {"connector": "MyConnector"}

    def test_model_dump(self):
        """Test serializing request to dict."""
        request = JsonRpcRequest(method="test", id=1, params={"key": "value"})
        data = request.model_dump(exclude_none=True)
        assert data["jsonrpc"] == "2.0"
        assert data["method"] == "test"
        assert data["id"] == 1
        assert data["params"] == {"key": "value"}

    def test_model_dump_no_params(self):
        """Test serializing request without params excludes None."""
        request = JsonRpcRequest(method="test", id=1)
        data = request.model_dump(exclude_none=True)
        assert "params" not in data


class TestJsonRpcResponse:
    """Tests for JsonRpcResponse."""

    def test_success_response(self):
        """Test creating success response."""
        response = JsonRpcResponse.success(1, {"status": "ok"})
        assert response.id == 1
        assert response.result == {"status": "ok"}
        assert response.error is None

    def test_error_response(self):
        """Test creating error response."""
        response = JsonRpcResponse.error_response(1, ErrorCode.INVALID_PARAMS, "bad param")
        assert response.id == 1
        assert response.result is None
        assert response.error is not None
        assert response.error.code == ErrorCode.INVALID_PARAMS.value
        assert response.error.message == "bad param"

    def test_model_dump_success(self):
        """Test serializing success response."""
        response = JsonRpcResponse.success(1, {"data": "test"})
        data = response.model_dump()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert data["result"] == {"data": "test"}
        assert "error" not in data

    def test_model_dump_error(self):
        """Test serializing error response."""
        response = JsonRpcResponse.error_response(1, ErrorCode.INTERNAL_ERROR, "failed")
        data = response.model_dump()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert "result" not in data
        assert data["error"]["code"] == ErrorCode.INTERNAL_ERROR.value
        assert data["error"]["message"] == "failed"


class TestJsonRpcNotification:
    """Tests for JsonRpcNotification."""

    def test_model_dump(self):
        """Test serializing notification."""
        notification = JsonRpcNotification(method="log", params={"message": "test"})
        data = notification.model_dump(exclude_none=True)
        assert data["jsonrpc"] == "2.0"
        assert data["method"] == "log"
        assert data["params"] == {"message": "test"}
        assert "id" not in data


class TestErrorCode:
    """Tests for ErrorCode enum."""

    def test_error_codes_exist(self):
        """Test that expected error codes exist."""
        assert ErrorCode.PARSE_ERROR.value == -32700
        assert ErrorCode.INVALID_REQUEST.value == -32600
        assert ErrorCode.METHOD_NOT_FOUND.value == -32601
        assert ErrorCode.INVALID_PARAMS.value == -32602
        assert ErrorCode.INTERNAL_ERROR.value == -32603


class TestPhaseStartNotification:
    """Tests for PhaseStartNotification."""

    def test_to_notification(self):
        """Test converting to JsonRpcNotification."""
        phase_start = PhaseStartNotification(phase="transform", total_records=100)
        notification = phase_start.to_notification()
        assert notification.method == "phase_start"
        assert notification.params is not None
        assert notification.params["phase"] == "transform"
        assert notification.params["total_records"] == 100


class TestPhaseCompleteNotification:
    """Tests for PhaseCompleteNotification."""

    def test_to_notification_success(self):
        """Test successful phase completion."""
        phase_complete = PhaseCompleteNotification(
            phase="transform",
            records_processed=50,
            duration_ms=1234.5,
            success=True,
        )
        notification = phase_complete.to_notification()
        assert notification.method == "phase_complete"
        assert notification.params is not None
        assert notification.params["phase"] == "transform"
        assert notification.params["records_processed"] == 50
        assert notification.params["duration_ms"] == 1234.5
        assert notification.params["success"] is True

    def test_to_notification_failure(self):
        """Test failed phase completion."""
        phase_complete = PhaseCompleteNotification(
            phase="transform",
            records_processed=10,
            duration_ms=500.0,
            success=False,
            error="Transform failed",
        )
        notification = phase_complete.to_notification()
        assert notification.params is not None
        assert notification.params["success"] is False
        assert notification.params["error"] == "Transform failed"


class TestRecordFetchedNotification:
    """Tests for RecordFetchedNotification."""

    def test_to_notification(self):
        """Test record fetched notification."""
        record = RecordFetchedNotification(
            record_id="doc-123",
            index=5,
            data={"title": "Test Doc"},
        )
        notification = record.to_notification()
        assert notification.method == "record_fetched"
        assert notification.params is not None
        assert notification.params["record_id"] == "doc-123"
        assert notification.params["index"] == 5
        assert notification.params["data"] == {"title": "Test Doc"}


class TestLogNotification:
    """Tests for LogNotification."""

    def test_to_notification(self):
        """Test log notification."""
        log = LogNotification(level="info", message="Processing started")
        notification = log.to_notification()
        assert notification.method == "log"
        assert notification.params is not None
        assert notification.params["level"] == "info"
        assert notification.params["message"] == "Processing started"

    def test_to_notification_with_source(self):
        """Test log notification with source."""
        log = LogNotification(level="error", message="Failed", source="MyConnector")
        notification = log.to_notification()
        assert notification.params is not None
        assert notification.params["source"] == "MyConnector"


class TestTransformCompleteNotification:
    """Tests for TransformCompleteNotification."""

    def test_to_notification(self):
        """Test transform complete notification."""
        transform = TransformCompleteNotification(
            record_id="doc-1",
            index=0,
            input_data={"raw": "data"},
            output_data={"id": "doc-1", "title": "Transformed"},
            field_mappings=[{"source_field": "raw", "target_field": "title"}],
            duration_ms=15.5,
        )
        notification = transform.to_notification()
        assert notification.method == "transform_complete"
        assert notification.params is not None
        assert notification.params["record_id"] == "doc-1"
        assert notification.params["input_data"] == {"raw": "data"}
        assert notification.params["output_data"]["title"] == "Transformed"
        assert len(notification.params["field_mappings"]) == 1


class TestTransformErrorNotification:
    """Tests for TransformErrorNotification."""

    def test_to_notification(self):
        """Test transform error notification."""
        error = TransformErrorNotification(
            record_id="doc-1",
            index=0,
            input_data={"bad": "data"},
            error="KeyError: 'required_field'",
            error_type="KeyError",
            traceback="Traceback...",
        )
        notification = error.to_notification()
        assert notification.method == "transform_error"
        assert notification.params is not None
        assert notification.params["record_id"] == "doc-1"
        assert notification.params["error_type"] == "KeyError"


class TestExecutionCompleteNotification:
    """Tests for ExecutionCompleteNotification."""

    def test_to_notification_success(self):
        """Test successful execution complete."""
        complete = ExecutionCompleteNotification(
            execution_id="exec-123",
            success=True,
            total_records=100,
            successful_records=95,
            failed_records=5,
            total_duration_ms=5000.0,
        )
        notification = complete.to_notification()
        assert notification.method == "execution_complete"
        assert notification.params is not None
        assert notification.params["execution_id"] == "exec-123"
        assert notification.params["success"] is True
        assert notification.params["total_records"] == 100
        assert notification.params["successful_records"] == 95
        assert notification.params["failed_records"] == 5


class TestHeartbeatNotification:
    """Tests for HeartbeatNotification."""

    def test_to_notification_with_message(self):
        """Test heartbeat notification with optional message."""
        heartbeat = HeartbeatNotification(
            phase="get_data",
            elapsed_seconds=4.5,
            message="Working on get_data...",
        )
        notification = heartbeat.to_notification()
        assert notification.method == "heartbeat"
        assert notification.params is not None
        assert notification.params["phase"] == "get_data"
        assert notification.params["elapsed_seconds"] == 4.5
        assert notification.params["message"] == "Working on get_data..."

    def test_to_notification_without_message(self):
        """Test heartbeat notification without optional message."""
        heartbeat = HeartbeatNotification(
            phase="transform",
            elapsed_seconds=10.0,
        )
        notification = heartbeat.to_notification()
        assert notification.method == "heartbeat"
        assert notification.params is not None
        assert notification.params["phase"] == "transform"
        assert notification.params["elapsed_seconds"] == 10.0
        assert "message" not in notification.params
