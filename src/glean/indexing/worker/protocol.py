"""JSON-RPC 2.0 protocol types for worker communication.

The worker uses JSON-RPC over stdin/stdout to communicate with Studio.
This follows similar patterns to LSP (Language Server Protocol).
"""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional, Union


class ErrorCode(IntEnum):
    """Standard JSON-RPC error codes."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # Custom error codes (application-specific)
    CONNECTOR_NOT_FOUND = -32000
    EXECUTION_ERROR = -32001
    PROJECT_ERROR = -32002


@dataclass
class JsonRpcError:
    """JSON-RPC error object."""

    code: int
    message: str
    data: Optional[Any] = None

    def to_dict(self) -> dict:
        result = {"code": self.code, "message": self.message}
        if self.data is not None:
            result["data"] = self.data
        return result


@dataclass
class JsonRpcRequest:
    """JSON-RPC request message."""

    method: str
    id: Union[str, int]
    params: Optional[dict] = None
    jsonrpc: str = "2.0"

    @classmethod
    def from_dict(cls, data: dict) -> "JsonRpcRequest":
        return cls(
            method=data["method"],
            id=data["id"],
            params=data.get("params"),
            jsonrpc=data.get("jsonrpc", "2.0"),
        )

    def to_dict(self) -> dict:
        result: dict = {"jsonrpc": self.jsonrpc, "method": self.method, "id": self.id}
        if self.params is not None:
            result["params"] = self.params
        return result


@dataclass
class JsonRpcResponse:
    """JSON-RPC response message."""

    id: Union[str, int, None]
    result: Optional[Any] = None
    error: Optional[JsonRpcError] = None
    jsonrpc: str = "2.0"

    def to_dict(self) -> dict:
        result: dict = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            result["error"] = self.error.to_dict()
        else:
            result["result"] = self.result
        return result

    @classmethod
    def success(cls, id: Union[str, int], result: Any) -> "JsonRpcResponse":
        return cls(id=id, result=result)

    @classmethod
    def error_response(
        cls,
        id: Union[str, int, None],
        code: int,
        message: str,
        data: Optional[Any] = None,
    ) -> "JsonRpcResponse":
        return cls(id=id, error=JsonRpcError(code=code, message=message, data=data))


@dataclass
class JsonRpcNotification:
    """JSON-RPC notification message (no id, no response expected)."""

    method: str
    params: Optional[dict] = None
    jsonrpc: str = "2.0"

    def to_dict(self) -> dict:
        result: dict = {"jsonrpc": self.jsonrpc, "method": self.method}
        if self.params is not None:
            result["params"] = self.params
        return result


# Worker-specific notification types


@dataclass
class PhaseStartNotification:
    """Notification when a phase starts."""

    phase: str
    total_records: Optional[int] = None

    def to_notification(self) -> JsonRpcNotification:
        return JsonRpcNotification(
            method="phase_start",
            params={
                "phase": self.phase,
                "total_records": self.total_records,
            },
        )


@dataclass
class PhaseCompleteNotification:
    """Notification when a phase completes."""

    phase: str
    records_processed: int
    duration_ms: float
    success: bool = True
    error: Optional[str] = None

    def to_notification(self) -> JsonRpcNotification:
        return JsonRpcNotification(
            method="phase_complete",
            params={
                "phase": self.phase,
                "records_processed": self.records_processed,
                "duration_ms": self.duration_ms,
                "success": self.success,
                "error": self.error,
            },
        )


@dataclass
class RecordFetchedNotification:
    """Notification when a record is fetched."""

    record_id: str
    index: int
    data: dict

    def to_notification(self) -> JsonRpcNotification:
        return JsonRpcNotification(
            method="record_fetched",
            params={
                "record_id": self.record_id,
                "index": self.index,
                "data": self.data,
            },
        )


@dataclass
class TransformCompleteNotification:
    """Notification when a record transformation completes."""

    record_id: str
    index: int
    input_data: dict
    output_data: dict
    field_mappings: list
    duration_ms: float

    def to_notification(self) -> JsonRpcNotification:
        return JsonRpcNotification(
            method="transform_complete",
            params={
                "record_id": self.record_id,
                "index": self.index,
                "input_data": self.input_data,
                "output_data": self.output_data,
                "field_mappings": self.field_mappings,
                "duration_ms": self.duration_ms,
            },
        )


@dataclass
class TransformErrorNotification:
    """Notification when a record transformation fails."""

    record_id: str
    index: int
    input_data: dict
    error: str
    error_type: str
    traceback: Optional[str] = None

    def to_notification(self) -> JsonRpcNotification:
        return JsonRpcNotification(
            method="transform_error",
            params={
                "record_id": self.record_id,
                "index": self.index,
                "input_data": self.input_data,
                "error": self.error,
                "error_type": self.error_type,
                "traceback": self.traceback,
            },
        )


@dataclass
class LogNotification:
    """Notification for log messages."""

    level: str  # 'debug', 'info', 'warning', 'error'
    message: str
    source: Optional[str] = None

    def to_notification(self) -> JsonRpcNotification:
        return JsonRpcNotification(
            method="log",
            params={
                "level": self.level,
                "message": self.message,
                "source": self.source,
            },
        )


@dataclass
class ExecutionCompleteNotification:
    """Notification when execution completes."""

    execution_id: str
    success: bool
    total_records: int
    successful_records: int
    failed_records: int
    total_duration_ms: float

    def to_notification(self) -> JsonRpcNotification:
        return JsonRpcNotification(
            method="execution_complete",
            params={
                "execution_id": self.execution_id,
                "success": self.success,
                "total_records": self.total_records,
                "successful_records": self.successful_records,
                "failed_records": self.failed_records,
                "total_duration_ms": self.total_duration_ms,
            },
        )


@dataclass
class HeartbeatNotification:
    """Notification to indicate the worker is still alive and working."""

    phase: str
    elapsed_seconds: float
    message: Optional[str] = None

    def to_notification(self) -> JsonRpcNotification:
        return JsonRpcNotification(
            method="heartbeat",
            params={
                "phase": self.phase,
                "elapsed_seconds": self.elapsed_seconds,
                "message": self.message,
            },
        )
