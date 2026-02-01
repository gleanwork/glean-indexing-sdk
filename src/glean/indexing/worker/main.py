"""Main entry point for the worker process.

Reads JSON-RPC requests from stdin, dispatches to handlers, and writes
responses/notifications to stdout.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from glean.indexing.worker.discovery import ProjectDiscovery
from glean.indexing.worker.executor import ConnectorExecutor, ExecutionConfig
from glean.indexing.worker.protocol import (
    ErrorCode,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
)

logger = logging.getLogger(__name__)


class WorkerServer:
    """JSON-RPC server for the worker process."""

    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path
        self.discovery = ProjectDiscovery(project_path)
        self.executor: Optional[ConnectorExecutor] = None
        self._running = True

    def write_message(self, message: dict) -> None:
        """Write a JSON-RPC message to stdout."""
        line = json.dumps(message) + "\n"
        sys.stdout.write(line)
        sys.stdout.flush()

    def emit_notification(self, notification: JsonRpcNotification) -> None:
        """Emit a notification to the parent process."""
        self.write_message(notification.to_dict())

    def send_response(self, response: JsonRpcResponse) -> None:
        """Send a response to a request."""
        self.write_message(response.to_dict())

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
            elif method == "shutdown":
                self._running = False
                return JsonRpcResponse.success(request.id, {"status": "shutting_down"})
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

    async def _handle_initialize(
        self, request_id: Any, params: Dict[str, Any]
    ) -> JsonRpcResponse:
        """Handle the initialize request."""
        project_info = self.discovery.discover_project()
        connectors = self.discovery.discover_connectors()

        return JsonRpcResponse.success(
            request_id,
            {
                "server_version": "0.1.0",
                "project": {
                    "path": project_info.path,
                    "name": project_info.name,
                    "python_version": project_info.python_version,
                    "has_mock_data": project_info.has_mock_data,
                    "mock_data_path": project_info.mock_data_path,
                },
                "connectors": [
                    {
                        "class_name": c.class_name,
                        "module_path": c.module_path,
                        "source_type": c.source_type,
                        "base_classes": c.base_classes,
                        "methods": c.methods,
                        "docstring": c.docstring,
                        "category": c.category,
                        "data_clients": c.data_clients,
                    }
                    for c in connectors
                ],
                "capabilities": ["execute", "pause", "resume", "step", "abort"],
            },
        )

    async def _handle_discover(self, request_id: Any) -> JsonRpcResponse:
        """Handle the discover request."""
        connectors = self.discovery.discover_connectors()

        return JsonRpcResponse.success(
            request_id,
            {
                "connectors": [
                    {
                        "class_name": c.class_name,
                        "module_path": c.module_path,
                        "source_type": c.source_type,
                        "base_classes": c.base_classes,
                        "methods": c.methods,
                        "docstring": c.docstring,
                        "category": c.category,
                        "data_clients": c.data_clients,
                    }
                    for c in connectors
                ]
            },
        )

    async def _handle_execute(
        self, request_id: Any, params: Dict[str, Any]
    ) -> JsonRpcResponse:
        """Handle the execute request."""
        connector_name = params.get("connector")
        if not connector_name:
            return JsonRpcResponse.error_response(
                request_id,
                ErrorCode.INVALID_PARAMS,
                "Missing 'connector' parameter",
            )

        # Create executor
        self.executor = ConnectorExecutor(
            project_path=self.project_path,
            emit_notification=self.emit_notification,
        )

        config = ExecutionConfig(
            step_mode=params.get("step_mode", False),
            mock_data_path=params.get("mock_data_path"),
        )

        # Start execution in background
        execution_id = self.executor.execution_id

        # Return immediately with execution ID
        asyncio.create_task(self._run_execution(connector_name, config))

        return JsonRpcResponse.success(
            request_id,
            {"execution_id": self.executor.execution_id, "status": "started"},
        )

    async def _run_execution(
        self, connector_name: str, config: ExecutionConfig
    ) -> None:
        """Run the execution in the background."""
        if self.executor:
            try:
                await self.executor.execute(connector_name, config)
            except Exception as e:
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

    async def run(self) -> None:
        """Main loop: read from stdin, dispatch, write to stdout."""
        logger.info(f"Worker started for project: {self.project_path}")

        loop = asyncio.get_event_loop()

        while self._running:
            try:
                # Read line from stdin (blocking in executor)
                line = await loop.run_in_executor(None, sys.stdin.readline)

                if not line:
                    # EOF - parent closed stdin
                    break

                line = line.strip()
                if not line:
                    continue

                # Parse JSON-RPC request
                try:
                    data = json.loads(line)
                except json.JSONDecodeError as e:
                    self.send_response(
                        JsonRpcResponse.error_response(
                            None,
                            ErrorCode.PARSE_ERROR,
                            f"Invalid JSON: {e}",
                        )
                    )
                    continue

                # Check if it's a valid request
                if "method" not in data or "id" not in data:
                    self.send_response(
                        JsonRpcResponse.error_response(
                            data.get("id"),
                            ErrorCode.INVALID_REQUEST,
                            "Missing 'method' or 'id'",
                        )
                    )
                    continue

                request = JsonRpcRequest.from_dict(data)
                response = await self.handle_request(request)
                self.send_response(response)

            except Exception as e:
                logger.exception("Error in main loop")
                self.send_response(
                    JsonRpcResponse.error_response(
                        None,
                        ErrorCode.INTERNAL_ERROR,
                        str(e),
                    )
                )

        logger.info("Worker shutting down")


def main() -> None:
    """Entry point for the worker."""
    # Configure logging to stderr
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    # Get project path from current directory
    project_path = Path.cwd()

    # Load .env file from project directory if present
    env_path = project_path / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
            logger.info(f"Loaded environment from {env_path}")
        except ImportError:
            logger.debug("python-dotenv not installed, skipping .env loading")

    # Create and run server
    server = WorkerServer(project_path)
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
