"""Request handlers for the worker process.

Transport-independent request handling logic. Used by both stdio and HTTP transports.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from glean.indexing.worker.discovery import ProjectDiscovery
from glean.indexing.worker.executor import ConnectorExecutor, ExecutionConfig
from glean.indexing.worker.protocol import (
    ErrorCode,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
)

logger = logging.getLogger(__name__)


class ExecuteParams(BaseModel):
    """Validated parameters for the execute request."""

    connector: str
    step_mode: bool = False
    mock_data_path: str | None = None


class RequestHandler:
    """Handles JSON-RPC requests independent of transport."""

    def __init__(
        self,
        project_path: Path,
        emit_notification: Callable[[JsonRpcNotification], None],
    ) -> None:
        self.project_path = project_path
        self.emit_notification = emit_notification
        self.discovery = ProjectDiscovery(project_path)
        self.executor: ConnectorExecutor | None = None
        self._execution_task: asyncio.Task | None = None

    async def handle_request(self, request: JsonRpcRequest) -> JsonRpcResponse:
        """Handle a JSON-RPC request and return a response."""
        method = request.method
        params = request.params or {}

        try:
            if method == "initialize":
                return await self._handle_initialize(request.id, params)
            elif method == "discover":
                return await self._handle_discover(request.id)
            elif method == "execute":
                return await self._handle_execute(request.id, params)
            elif method == "pause":
                return await self._handle_pause(request.id)
            elif method == "resume":
                return await self._handle_resume(request.id)
            elif method == "step":
                return await self._handle_step(request.id)
            elif method == "abort":
                return await self._handle_abort(request.id)
            else:
                return JsonRpcResponse.error_response(
                    request.id,
                    ErrorCode.METHOD_NOT_FOUND,
                    f"Method not found: {method}",
                )
        except Exception as e:
            logger.exception(f"Error handling request {method}")
            return JsonRpcResponse.error_response(
                request.id,
                ErrorCode.INTERNAL_ERROR,
                str(e),
            )

    async def _handle_initialize(self, request_id: Any, params: dict[str, Any]) -> JsonRpcResponse:
        """Handle the initialize request."""
        project_info = self.discovery.discover_project()
        connectors = self.discovery.discover_connectors()

        return JsonRpcResponse.success(
            request_id,
            {
                "server_version": "0.1.0",
                "project": project_info.model_dump(exclude_none=True),
                "connectors": [c.model_dump(exclude_none=True) for c in connectors],
                "capabilities": ["execute", "pause", "resume", "step", "abort"],
            },
        )

    async def _handle_discover(self, request_id: Any) -> JsonRpcResponse:
        """Handle the discover request."""
        connectors = self.discovery.discover_connectors()

        return JsonRpcResponse.success(
            request_id,
            {
                "connectors": [c.model_dump(exclude_none=True) for c in connectors],
            },
        )

    async def _handle_execute(self, request_id: Any, params: dict[str, Any]) -> JsonRpcResponse:
        """Handle the execute request."""
        try:
            execute_params = ExecuteParams.model_validate(params)
        except ValidationError as e:
            return JsonRpcResponse.error_response(
                request_id,
                ErrorCode.INVALID_PARAMS,
                f"Invalid execute parameters: {e}",
            )

        # Reject if an execution is already running
        if self._execution_task is not None and not self._execution_task.done():
            return JsonRpcResponse.error_response(
                request_id,
                ErrorCode.EXECUTION_ERROR,
                "An execution is already in progress",
            )

        # Create executor
        self.executor = ConnectorExecutor(
            project_path=self.project_path,
            emit_notification=self.emit_notification,
        )

        config = ExecutionConfig(
            step_mode=execute_params.step_mode,
            mock_data_path=execute_params.mock_data_path,
        )

        self._execution_task = asyncio.create_task(
            self._run_execution(execute_params.connector, config)
        )

        return JsonRpcResponse.success(
            request_id,
            {"execution_id": self.executor.execution_id, "status": "started"},
        )

    async def _run_execution(self, connector_name: str, config: ExecutionConfig) -> None:
        """Run the execution in the background."""
        if self.executor:
            try:
                await self.executor.execute(connector_name, config)
            except Exception:
                logger.exception("Execution failed")

    async def _handle_pause(self, request_id: Any) -> JsonRpcResponse:
        """Handle the pause request."""
        if not self.executor:
            return JsonRpcResponse.error_response(
                request_id,
                ErrorCode.EXECUTION_ERROR,
                "No execution in progress",
            )

        self.executor.pause()
        return JsonRpcResponse.success(request_id, {"status": "paused"})

    async def _handle_resume(self, request_id: Any) -> JsonRpcResponse:
        """Handle the resume request."""
        if not self.executor:
            return JsonRpcResponse.error_response(
                request_id,
                ErrorCode.EXECUTION_ERROR,
                "No execution in progress",
            )

        self.executor.resume()
        return JsonRpcResponse.success(request_id, {"status": "resumed"})

    async def _handle_step(self, request_id: Any) -> JsonRpcResponse:
        """Handle the step request."""
        if not self.executor:
            return JsonRpcResponse.error_response(
                request_id,
                ErrorCode.EXECUTION_ERROR,
                "No execution in progress",
            )

        self.executor.step()
        return JsonRpcResponse.success(request_id, {"status": "stepped"})

    async def _handle_abort(self, request_id: Any) -> JsonRpcResponse:
        """Handle the abort request."""
        if not self.executor:
            return JsonRpcResponse.error_response(
                request_id,
                ErrorCode.EXECUTION_ERROR,
                "No execution in progress",
            )

        self.executor.abort()
        return JsonRpcResponse.success(request_id, {"status": "aborted"})
