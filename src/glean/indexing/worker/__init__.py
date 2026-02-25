"""Worker module for executing Glean indexing connectors.

This module provides a subprocess-based worker that can be spawned by an
orchestrator (such as the Glean MCP server) to discover and execute
connectors in their project's virtual environment.

Usage:
    cd /path/to/connector/project
    uv run python -m glean.indexing.worker

The worker communicates with its parent process via JSON-RPC over stdin/stdout.
"""

from glean.indexing.worker.discovery import ConnectorInfo, ProjectDiscovery, ProjectInfo
from glean.indexing.worker.executor import ConnectorExecutor, ExecutionConfig, ExecutionState
from glean.indexing.worker.handlers import RequestHandler
from glean.indexing.worker.main import StdioWorkerServer
from glean.indexing.worker.protocol import (
    ErrorCode,
    JsonRpcError,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
)

__all__ = [
    "ConnectorExecutor",
    "ConnectorInfo",
    "ErrorCode",
    "ExecutionConfig",
    "ExecutionState",
    "JsonRpcError",
    "JsonRpcNotification",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "ProjectDiscovery",
    "ProjectInfo",
    "RequestHandler",
    "StdioWorkerServer",
]
