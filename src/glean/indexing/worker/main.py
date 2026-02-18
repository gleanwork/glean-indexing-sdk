"""Stdio transport for the worker process.

Reads JSON-RPC requests from stdin, dispatches to handlers, and writes
responses/notifications to stdout.

The worker automatically exits when:
- stdin is closed (parent process died)
- SIGTERM or SIGINT is received
- Parent process ID changes to 1 (orphaned on Unix)
"""

import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any

from glean.indexing.worker.handlers import RequestHandler
from glean.indexing.worker.protocol import (
    ErrorCode,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
)

logger = logging.getLogger(__name__)


class StdioWorkerServer:
    """JSON-RPC server for the worker process using stdio transport."""

    def __init__(self, project_path: Path) -> None:
        """Initialize the server.

        Args:
            project_path: Path to the connector project.
        """
        self.project_path = project_path
        self._running = True
        self._parent_pid = os.getppid()
        self._setup_signal_handlers()

        # Create the request handler with stdio notification emitter
        self.handler = RequestHandler(
            project_path=project_path,
            emit_notification=self.emit_notification,
        )

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""

        def handle_signal(signum: int, frame: Any) -> None:
            logger.info(f"Received signal {signum}, shutting down")
            self._running = False

        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)

    def _check_parent_alive(self) -> bool:
        """Check if parent process is still alive.

        On Unix, when a parent process dies, the child is adopted by init (pid 1).
        We detect this to know when to exit.
        """
        current_ppid = os.getppid()
        if current_ppid != self._parent_pid:
            logger.info(
                f"Parent process changed from {self._parent_pid} to {current_ppid}, exiting"
            )
            return False
        return True

    def write_message(self, message: dict) -> None:
        """Write a JSON-RPC message to stdout."""
        line = json.dumps(message) + "\n"
        sys.stdout.write(line)
        sys.stdout.flush()

    def emit_notification(self, notification: JsonRpcNotification) -> None:
        """Emit a notification to the parent process."""
        self.write_message(notification.model_dump(exclude_none=True))

    def send_response(self, response: JsonRpcResponse) -> None:
        """Send a response to a request."""
        self.write_message(response.model_dump())

    async def run(self) -> None:
        """Main loop: read from stdin, dispatch, write to stdout."""
        logger.info(
            f"Worker started for project: {self.project_path} (parent pid: {self._parent_pid})"
        )

        loop = asyncio.get_event_loop()

        # Start parent watchdog
        watchdog_task = asyncio.create_task(self._parent_watchdog())

        # Create a queue for stdin lines (read in separate thread)
        stdin_queue: asyncio.Queue[str | None] = asyncio.Queue()

        # Start stdin reader in background thread
        def read_stdin() -> None:
            """Read lines from stdin and put them in the queue."""
            while self._running:
                try:
                    line = sys.stdin.readline()
                    if not line:
                        # EOF
                        asyncio.run_coroutine_threadsafe(stdin_queue.put(None), loop)
                        break
                    asyncio.run_coroutine_threadsafe(stdin_queue.put(line), loop)
                except Exception:
                    break

        loop.run_in_executor(None, read_stdin)

        try:
            while self._running:
                try:
                    # Wait for line from queue with timeout
                    try:
                        line = await asyncio.wait_for(stdin_queue.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        # No input, just loop to check _running flag
                        continue

                    if line is None:
                        # EOF - parent closed stdin
                        logger.info("stdin closed, exiting")
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

                    request = JsonRpcRequest.model_validate(data)

                    # Handle shutdown specially (transport concern, not handler concern)
                    if request.method == "shutdown":
                        self._running = False
                        self.send_response(
                            JsonRpcResponse.success(request.id, {"status": "shutting_down"})
                        )
                        continue

                    response = await self.handler.handle_request(request)
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
        finally:
            # Cancel the watchdog task
            watchdog_task.cancel()
            try:
                await watchdog_task
            except asyncio.CancelledError:
                pass

        logger.info("Worker shutting down")

    async def _parent_watchdog(self) -> None:
        """Periodically check if parent process is still alive."""
        while self._running:
            await asyncio.sleep(2.0)  # Check every 2 seconds
            if not self._check_parent_alive():
                self._running = False
                break


def run_stdio_server(project_path: Path) -> None:
    """Run the worker in stdio mode.

    Args:
        project_path: Path to the connector project.
    """
    server = StdioWorkerServer(project_path)
    asyncio.run(server.run())
