"""Worker module for Glean Connector Studio.

This module provides a minimal worker that can be spawned as a subprocess
by Studio to execute connectors in their project's virtual environment.

Usage:
    cd /path/to/connector/project
    uv run python -m glean.indexing.worker

The worker communicates with Studio via JSON-RPC over stdin/stdout.
"""

from glean.indexing.worker.protocol import (
    JsonRpcRequest,
    JsonRpcResponse,
    JsonRpcNotification,
    JsonRpcError,
    ErrorCode,
)

__all__ = [
    "JsonRpcRequest",
    "JsonRpcResponse",
    "JsonRpcNotification",
    "JsonRpcError",
    "ErrorCode",
]
