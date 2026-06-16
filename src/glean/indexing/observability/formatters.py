"""Structured logging formatters for Glean connectors.

Provides JSON formatters compatible with stdlib logging that make logs
machine-readable while preserving the standard logging.Handler interface.
"""

import json
import logging
import traceback
from datetime import datetime
from typing import Any, Dict, Optional


class StructuredFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.

    Serializes log records to JSON format while preserving all standard
    logging metadata. Compatible with stdlib logging handlers.

    Features:
    - Automatic JSON serialization of log metadata
    - Merges fields passed via logger.info("msg", extra={...})
    - Handles exception formatting
    - Omits noisy internal LogRecord attributes
    - ISO 8601 timestamps

    Example:
        >>> import logging
        >>> handler = logging.StreamHandler()
        >>> handler.setFormatter(StructuredFormatter())
        >>> logger = logging.getLogger(__name__)
        >>> logger.addHandler(handler)
        >>> logger.info("Processing batch", extra={"batch_id": "123", "count": 50})

    Output:
        {"timestamp": "2026-05-28T18:00:00.000Z", "level": "INFO",
         "logger": "mymodule", "message": "Processing batch",
         "batch_id": "123", "count": 50}
    """

    _STANDARD_LOG_RECORD_ATTRS: frozenset = frozenset(logging.makeLogRecord({}).__dict__)

    def __init__(
        self,
        include_timestamp: bool = True,
        timestamp_field: str = "timestamp",
        level_field: str = "level",
        logger_field: str = "logger",
        message_field: str = "message",
        exception_field: str = "exception",
        extra_fields: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the structured formatter.

        Args:
            include_timestamp: Include timestamp in output (default: True)
            timestamp_field: Field name for timestamp (default: "timestamp")
            level_field: Field name for log level (default: "level")
            logger_field: Field name for logger name (default: "logger")
            message_field: Field name for message (default: "message")
            exception_field: Field name for exception details (default: "exception")
            extra_fields: Additional fields to include in every log record
        """
        super().__init__()
        self.include_timestamp = include_timestamp
        self.timestamp_field = timestamp_field
        self.level_field = level_field
        self.logger_field = logger_field
        self.message_field = message_field
        self.exception_field = exception_field
        self.extra_fields = extra_fields or {}

    def _build_log_data(self, record: logging.LogRecord) -> Dict[str, Any]:
        log_data: Dict[str, Any] = {}

        log_data.update(self.extra_fields)

        if self.include_timestamp:
            log_data[self.timestamp_field] = datetime.utcfromtimestamp(
                record.created
            ).isoformat() + "Z"

        log_data[self.level_field] = record.levelname
        log_data[self.logger_field] = record.name
        log_data[self.message_field] = record.getMessage()

        reserved_output_fields = {
            self.timestamp_field,
            self.level_field,
            self.logger_field,
            self.message_field,
            self.exception_field,
        }
        for key, value in record.__dict__.items():
            if (
                key not in self._STANDARD_LOG_RECORD_ATTRS
                and key not in reserved_output_fields
                and not key.startswith("_")
            ):
                log_data[key] = value

        exc_info = record.exc_info
        if isinstance(exc_info, tuple) and len(exc_info) >= 2 and exc_info[0] is not None:
            log_data[self.exception_field] = {
                "type": exc_info[0].__name__,
                "message": str(exc_info[1]) if exc_info[1] else None,
                "traceback": self._format_exception(exc_info),
            }

        return log_data

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string."""
        log_data = self._build_log_data(record)

        try:
            return json.dumps(log_data, default=str)
        except (TypeError, ValueError) as e:
            return json.dumps(
                {
                    self.level_field: "ERROR",
                    self.message_field: f"Failed to serialize log record: {e}",
                    "original_message": str(record.msg),
                }
            )

    def _format_exception(self, exc_info) -> str:
        if not exc_info:
            return ""

        try:
            return "".join(traceback.format_exception(*exc_info)).strip()
        except Exception:
            return str(exc_info)


class CompactStructuredFormatter(StructuredFormatter):
    """
    Compact JSON formatter that omits empty/null fields.

    Extends StructuredFormatter but produces smaller output by:
    - Omitting null/None values
    - Omitting empty strings, lists, and dicts
    - Useful for high-volume logging scenarios

    Example:
        >>> handler.setFormatter(CompactStructuredFormatter())
        >>> logger.info("Done")
        {"timestamp": "2026-05-28T18:00:00.000Z", "level": "INFO", "logger": "mymodule", "message": "Done"}
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string, omitting empty/null fields."""
        log_data = self._build_log_data(record)

        filtered_data = {
            k: v
            for k, v in log_data.items()
            if v not in (None, "", [], {})
        }

        try:
            return json.dumps(filtered_data, default=str)
        except (TypeError, ValueError) as e:
            return json.dumps(
                {
                    self.level_field: "ERROR",
                    self.message_field: f"Failed to serialize log record: {e}",
                    "original_message": str(record.msg),
                }
            )
