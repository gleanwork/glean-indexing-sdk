"""JSON-RPC 2.0 protocol types for worker communication.

The worker uses JSON-RPC over stdin/stdout to communicate with Studio.
This follows similar patterns to LSP (Language Server Protocol).
"""

from enum import IntEnum
from typing import Any, ClassVar

from pydantic import BaseModel


class ErrorCode(IntEnum):
    """Standard JSON-RPC error codes plus worker-specific extensions."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    CONNECTOR_NOT_FOUND = -32000
    EXECUTION_ERROR = -32001
    PROJECT_ERROR = -32002


class JsonRpcError(BaseModel):
    """JSON-RPC error object."""

    code: int
    message: str
    data: Any | None = None


class JsonRpcRequest(BaseModel):
    """JSON-RPC request message."""

    method: str
    id: str | int
    params: dict | None = None
    jsonrpc: str = "2.0"


class JsonRpcResponse(BaseModel):
    """JSON-RPC response message."""

    id: str | int | None
    result: Any | None = None
    error: JsonRpcError | None = None
    jsonrpc: str = "2.0"

    def model_dump(self, **kwargs: Any) -> dict:
        """Serialize with error XOR result, never both."""
        result: dict = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            result["error"] = self.error.model_dump(exclude_none=True)
        else:
            result["result"] = self.result
        return result

    @classmethod
    def success(cls, id: str | int, result: Any) -> "JsonRpcResponse":
        return cls(id=id, result=result)

    @classmethod
    def error_response(
        cls,
        id: str | int | None,
        code: int,
        message: str,
        data: Any | None = None,
    ) -> "JsonRpcResponse":
        return cls(id=id, error=JsonRpcError(code=code, message=message, data=data))


class JsonRpcNotification(BaseModel):
    """JSON-RPC notification (no id, no response expected)."""

    method: str
    params: dict | None = None
    jsonrpc: str = "2.0"


class BaseNotification(BaseModel):
    """Base for typed notification payloads.

    Subclasses set ``notification_method`` and define their fields.
    Call ``to_notification()`` to wrap into a ``JsonRpcNotification``.
    """

    notification_method: ClassVar[str]

    def to_notification(self) -> JsonRpcNotification:
        return JsonRpcNotification(
            method=self.notification_method,
            params=self.model_dump(exclude_none=True),
        )


class PhaseStartNotification(BaseNotification):
    notification_method: ClassVar[str] = "phase_start"
    phase: str
    total_records: int | None = None


class PhaseCompleteNotification(BaseNotification):
    notification_method: ClassVar[str] = "phase_complete"
    phase: str
    records_processed: int
    duration_ms: float
    success: bool = True
    error: str | None = None


class RecordFetchedNotification(BaseNotification):
    notification_method: ClassVar[str] = "record_fetched"
    record_id: str
    index: int
    data: dict


class TransformCompleteNotification(BaseNotification):
    notification_method: ClassVar[str] = "transform_complete"
    record_id: str
    index: int
    input_data: dict
    output_data: dict
    field_mappings: list
    duration_ms: float


class TransformErrorNotification(BaseNotification):
    notification_method: ClassVar[str] = "transform_error"
    record_id: str
    index: int
    input_data: dict
    error: str
    error_type: str
    traceback: str | None = None


class LogNotification(BaseNotification):
    notification_method: ClassVar[str] = "log"
    level: str
    message: str
    source: str | None = None


class ExecutionCompleteNotification(BaseNotification):
    notification_method: ClassVar[str] = "execution_complete"
    execution_id: str
    success: bool
    total_records: int
    successful_records: int
    failed_records: int
    total_duration_ms: float


class HeartbeatNotification(BaseNotification):
    notification_method: ClassVar[str] = "heartbeat"
    phase: str
    elapsed_seconds: float
    message: str | None = None
