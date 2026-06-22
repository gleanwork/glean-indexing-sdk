"""Logging configuration recipes for connectors."""

import logging

from glean.indexing.observability import (
    CompactStructuredFormatter,
    StructuredFormatter,
    setup_connector_logging,
)


def setup_basic_logging(connector_name: str) -> None:
    """Configure human-readable console logging."""
    setup_connector_logging(connector_name, log_level="INFO", use_structured_logging=False)


def setup_debug_logging(connector_name: str) -> None:
    """Configure verbose debug logging."""
    setup_connector_logging(connector_name, log_level="DEBUG", use_structured_logging=False)


def setup_structured_logging(connector_name: str) -> None:
    """Configure JSON structured logging for production."""
    setup_connector_logging(connector_name, use_structured_logging=True)


def setup_compact_structured_logging(connector_name: str) -> None:
    """Configure compact JSON logging that omits empty fields."""
    formatter = CompactStructuredFormatter()
    setup_connector_logging(connector_name, formatter=formatter)


def setup_custom_format_logging(connector_name: str) -> None:
    """Configure custom log format string."""
    setup_connector_logging(
        connector_name,
        log_level="INFO",
        log_format="%(levelname)s - %(name)s - %(message)s",
    )


def setup_multi_handler_logging(connector_name: str, log_file_path: str) -> None:
    """Configure logging to both console and file."""
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(StructuredFormatter())

    setup_connector_logging(
        connector_name,
        use_structured_logging=True,
        extra_handlers=[file_handler],
    )


def setup_custom_structured_fields(connector_name: str, environment: str, version: str) -> None:
    """Configure structured logging with extra fields in every log."""
    formatter = StructuredFormatter(
        extra_fields={
            "environment": environment,
            "version": version,
            "service": connector_name,
        }
    )
    setup_connector_logging(connector_name, formatter=formatter)


if __name__ == "__main__":
    setup_basic_logging("example_connector")

    logger = logging.getLogger(__name__)
    logger.info("Basic logging configured")
    logger.debug("This won't appear with INFO level")

    setup_structured_logging("example_connector")
    logger.info("Structured logging configured", extra={"batch_id": "123", "count": 50})
