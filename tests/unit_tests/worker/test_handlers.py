"""Tests for RequestHandler JSON-RPC request handling."""

from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from glean.indexing.worker.handlers import ExecuteParams, RequestHandler
from glean.indexing.worker.protocol import (
    ErrorCode,
    JsonRpcRequest,
    JsonRpcResponse,
)

# --- ExecuteParams validation ---


class TestExecuteParams:
    """Tests for ExecuteParams Pydantic model."""

    def test_valid_minimal(self):
        """Test validation with only required fields."""
        params = ExecuteParams.model_validate({"connector": "MyConnector"})
        assert params.connector == "MyConnector"
        assert params.step_mode is False
        assert params.mock_data_path is None

    def test_valid_all_fields(self):
        """Test validation with all fields provided."""
        params = ExecuteParams.model_validate(
            {
                "connector": "MyConnector",
                "step_mode": True,
                "mock_data_path": "/tmp/mock.json",
            }
        )
        assert params.connector == "MyConnector"
        assert params.step_mode is True
        assert params.mock_data_path == "/tmp/mock.json"

    def test_missing_required_connector(self):
        """Test validation fails when connector is missing."""
        with pytest.raises(Exception):
            ExecuteParams.model_validate({"step_mode": True})


# --- handle_request dispatch ---


def _result(response: JsonRpcResponse) -> dict[str, Any]:
    """Extract result from response, asserting it is not None."""
    assert response.result is not None
    return cast(dict[str, Any], response.result)


def _make_handler(tmp_path: Path) -> RequestHandler:
    """Create a RequestHandler with a no-op notification emitter."""
    return RequestHandler(
        project_path=tmp_path,
        emit_notification=lambda n: None,
    )


class TestHandleRequest:
    """Tests for RequestHandler.handle_request dispatching."""

    @pytest.fixture()
    def handler(self, tmp_path: Path) -> RequestHandler:
        return _make_handler(tmp_path)

    @pytest.mark.asyncio
    async def test_initialize(self, handler: RequestHandler):
        """Test initialize returns server info."""
        request = JsonRpcRequest(method="initialize", id=1, params={})
        response = await handler.handle_request(request)
        assert response.error is None
        result = _result(response)
        assert result["server_version"] == "0.1.0"
        assert "connectors" in result
        assert "capabilities" in result

    @pytest.mark.asyncio
    async def test_discover(self, handler: RequestHandler):
        """Test discover returns connectors list."""
        request = JsonRpcRequest(method="discover", id=2)
        response = await handler.handle_request(request)
        assert response.error is None
        result = _result(response)
        assert "connectors" in result

    @pytest.mark.asyncio
    async def test_execute_invalid_params(self, handler: RequestHandler):
        """Test execute with missing connector param returns INVALID_PARAMS."""
        request = JsonRpcRequest(method="execute", id=3, params={"step_mode": True})
        response = await handler.handle_request(request)
        assert response.error is not None
        assert response.error.code == ErrorCode.INVALID_PARAMS

    @pytest.mark.asyncio
    async def test_execute_valid_params(self, handler: RequestHandler):
        """Test execute with valid params starts execution."""
        request = JsonRpcRequest(
            method="execute",
            id=4,
            params={"connector": "FakeConnector"},
        )
        response = await handler.handle_request(request)
        assert response.error is None
        result = _result(response)
        assert result["status"] == "started"
        assert result["execution_id"] is not None
        assert handler.executor is not None

    @pytest.mark.asyncio
    async def test_execute_while_running_rejected(self, handler: RequestHandler):
        """Test that a second execute while one is running returns EXECUTION_ERROR."""
        # Start first execution
        request1 = JsonRpcRequest(
            method="execute",
            id=5,
            params={"connector": "FakeConnector"},
        )
        response1 = await handler.handle_request(request1)
        assert response1.error is None

        # Try to start a second execution while the first task is still pending
        request2 = JsonRpcRequest(
            method="execute",
            id=6,
            params={"connector": "AnotherConnector"},
        )
        response2 = await handler.handle_request(request2)
        assert response2.error is not None
        assert response2.error.code == ErrorCode.EXECUTION_ERROR
        assert "already in progress" in response2.error.message

    @pytest.mark.asyncio
    async def test_unknown_method(self, handler: RequestHandler):
        """Test unknown method returns METHOD_NOT_FOUND."""
        request = JsonRpcRequest(method="nonexistent", id=11)
        response = await handler.handle_request(request)
        assert response.error is not None
        assert response.error.code == ErrorCode.METHOD_NOT_FOUND


# --- Error handling ---


class TestHandleRequestErrors:
    """Tests for error handling in handle_request."""

    @pytest.mark.asyncio
    async def test_exception_in_handler(self, tmp_path: Path):
        """Test that an exception in a handler returns INTERNAL_ERROR."""
        handler = _make_handler(tmp_path)
        # Patch _handle_initialize to raise
        with patch.object(handler, "_handle_initialize", side_effect=RuntimeError("boom")):
            request = JsonRpcRequest(method="initialize", id=99)
            response = await handler.handle_request(request)
        assert response.error is not None
        assert response.error.code == ErrorCode.INTERNAL_ERROR
        assert "boom" in response.error.message


# --- Control methods without active executor ---


class TestControlWithoutExecutor:
    """Tests for pause/resume/step/abort when no executor is active."""

    @pytest.fixture()
    def handler(self, tmp_path: Path) -> RequestHandler:
        return _make_handler(tmp_path)

    @pytest.mark.asyncio
    async def test_pause_no_executor(self, handler: RequestHandler):
        """Test pause without executor returns EXECUTION_ERROR."""
        request = JsonRpcRequest(method="pause", id=20)
        response = await handler.handle_request(request)
        assert response.error is not None
        assert response.error.code == ErrorCode.EXECUTION_ERROR
        assert "No execution in progress" in response.error.message

    @pytest.mark.asyncio
    async def test_resume_no_executor(self, handler: RequestHandler):
        """Test resume without executor returns EXECUTION_ERROR."""
        request = JsonRpcRequest(method="resume", id=21)
        response = await handler.handle_request(request)
        assert response.error is not None
        assert response.error.code == ErrorCode.EXECUTION_ERROR

    @pytest.mark.asyncio
    async def test_step_no_executor(self, handler: RequestHandler):
        """Test step without executor returns EXECUTION_ERROR."""
        request = JsonRpcRequest(method="step", id=22)
        response = await handler.handle_request(request)
        assert response.error is not None
        assert response.error.code == ErrorCode.EXECUTION_ERROR

    @pytest.mark.asyncio
    async def test_abort_no_executor(self, handler: RequestHandler):
        """Test abort without executor returns EXECUTION_ERROR."""
        request = JsonRpcRequest(method="abort", id=23)
        response = await handler.handle_request(request)
        assert response.error is not None
        assert response.error.code == ErrorCode.EXECUTION_ERROR


# --- Control methods with mock executor ---


class TestControlWithExecutor:
    """Tests for pause/resume/step/abort with a mock executor."""

    @pytest.fixture()
    def handler(self, tmp_path: Path) -> RequestHandler:
        h = _make_handler(tmp_path)
        h.executor = MagicMock()  # type: ignore[assignment]
        return h

    @pytest.mark.asyncio
    async def test_pause(self, handler: RequestHandler):
        """Test pause delegates to executor."""
        request = JsonRpcRequest(method="pause", id=30)
        response = await handler.handle_request(request)
        assert response.error is None
        result = _result(response)
        assert result["status"] == "paused"
        assert handler.executor is not None
        handler.executor.pause.assert_called_once()  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_resume(self, handler: RequestHandler):
        """Test resume delegates to executor."""
        request = JsonRpcRequest(method="resume", id=31)
        response = await handler.handle_request(request)
        assert response.error is None
        result = _result(response)
        assert result["status"] == "resumed"
        assert handler.executor is not None
        handler.executor.resume.assert_called_once()  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_step(self, handler: RequestHandler):
        """Test step delegates to executor."""
        request = JsonRpcRequest(method="step", id=32)
        response = await handler.handle_request(request)
        assert response.error is None
        result = _result(response)
        assert result["status"] == "stepped"
        assert handler.executor is not None
        handler.executor.step.assert_called_once()  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_abort(self, handler: RequestHandler):
        """Test abort delegates to executor."""
        request = JsonRpcRequest(method="abort", id=33)
        response = await handler.handle_request(request)
        assert response.error is None
        result = _result(response)
        assert result["status"] == "aborted"
        assert handler.executor is not None
        handler.executor.abort.assert_called_once()  # type: ignore[union-attr]
