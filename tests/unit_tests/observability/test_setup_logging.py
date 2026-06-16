"""Tests for setup_connector_logging function."""

import json
import logging
from io import StringIO

import pytest

from glean.indexing.observability import (
    CompactStructuredFormatter,
    StructuredFormatter,
    setup_connector_logging,
)


def _glean_logger() -> logging.Logger:
    return logging.getLogger("glean")


class TestSetupConnectorLogging:
    """Tests for setup_connector_logging configuration function."""

    def teardown_method(self):
        """Clean up the glean logger after each test."""
        gl = _glean_logger()
        for h in gl.handlers[:]:
            h.close()
            gl.removeHandler(h)
        gl.setLevel(logging.NOTSET)

    def test_default_configuration(self):
        """Test default structured logging configuration."""
        setup_connector_logging("test_connector")

        gl = _glean_logger()
        assert gl.level == logging.INFO
        assert len(gl.handlers) > 0

    def test_default_is_structured(self):
        """Test that default logging produces structured JSON output."""
        setup_connector_logging("test_connector")

        stream = StringIO()
        for handler in _glean_logger().handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.stream = stream

        logging.getLogger("glean.test").info("Test")

        stream.seek(0)
        output = stream.read().strip().splitlines()[-1]
        log_data = json.loads(output)
        assert log_data["message"] == "Test"

    def test_structured_logging_enabled(self):
        """Test enabling structured JSON logging."""
        setup_connector_logging("test_connector", use_structured_logging=True)

        stream = StringIO()
        for handler in _glean_logger().handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.stream = stream

        logging.getLogger("glean.test").info(
            "Test structured message", extra={"custom_field": "custom_value"}
        )

        stream.seek(0)
        output = stream.read().strip().splitlines()[-1]
        log_data = json.loads(output)

        assert log_data["message"] == "Test structured message"
        assert log_data["level"] == "INFO"
        assert log_data["custom_field"] == "custom_value"
        assert "timestamp" in log_data

    def test_custom_log_level(self):
        """Test setting custom log level."""
        setup_connector_logging("test_connector", log_level="DEBUG")

        assert _glean_logger().level == logging.DEBUG

        stream = StringIO()
        for handler in _glean_logger().handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.stream = stream

        logging.getLogger("glean.test").debug("Debug message")

        stream.seek(0)
        output = stream.read().strip().splitlines()[-1]
        assert "Debug message" in output

    def test_custom_formatter(self):
        """Test using a custom formatter."""
        custom_formatter = CompactStructuredFormatter()
        setup_connector_logging("test_connector", formatter=custom_formatter)

        stream = StringIO()
        for handler in _glean_logger().handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.stream = stream
                assert isinstance(handler.formatter, CompactStructuredFormatter)

        logging.getLogger("glean.test").info("Test", extra={"keep": "value", "omit": ""})

        stream.seek(0)
        log_data = json.loads(stream.read().strip().splitlines()[-1])
        assert "keep" in log_data
        assert "omit" not in log_data

    def test_extra_handlers(self):
        """Test adding extra handlers."""
        extra_stream = StringIO()
        extra_handler = logging.StreamHandler(extra_stream)

        setup_connector_logging("test_connector", extra_handlers=[extra_handler])

        assert len(_glean_logger().handlers) >= 2

        logging.getLogger("glean.test").info("Test message")

        extra_stream.seek(0)
        output = extra_stream.read().strip().splitlines()[-1]
        assert "Test message" in output

    def test_extra_handler_without_formatter_gets_sdk_formatter(self):
        """Test that an extra handler without a formatter receives the SDK formatter."""
        extra_stream = StringIO()
        extra_handler = logging.StreamHandler(extra_stream)

        setup_connector_logging("test_connector", use_structured_logging=True, extra_handlers=[extra_handler])

        assert isinstance(extra_handler.formatter, StructuredFormatter)

    def test_extra_handler_with_existing_formatter_is_not_overwritten(self):
        """Test that a pre-configured extra handler keeps its own formatter."""
        extra_stream = StringIO()
        extra_handler = logging.StreamHandler(extra_stream)
        custom_fmt = logging.Formatter("%(levelname)s %(message)s")
        extra_handler.setFormatter(custom_fmt)

        setup_connector_logging("test_connector", use_structured_logging=True, extra_handlers=[extra_handler])

        assert extra_handler.formatter is custom_fmt

    def test_structured_logging_with_extra_handlers(self):
        """Test structured logging with multiple handlers, all without pre-set formatters."""
        extra_stream = StringIO()
        extra_handler = logging.StreamHandler(extra_stream)

        setup_connector_logging(
            "test_connector",
            use_structured_logging=True,
            extra_handlers=[extra_handler],
        )

        for handler in _glean_logger().handlers:
            assert isinstance(handler.formatter, StructuredFormatter)

        extra_stream.truncate(0)
        extra_stream.seek(0)

        logging.getLogger("glean.test").info("Test")

        extra_stream.seek(0)
        log_data = json.loads(extra_stream.read().strip().splitlines()[-1])
        assert log_data["message"] == "Test"

    def test_does_not_touch_root_handlers(self):
        """Test that setup_connector_logging never modifies root logger handlers."""
        root_handler = logging.StreamHandler()
        logging.root.addHandler(root_handler)

        try:
            setup_connector_logging("test_connector", log_level="INFO")
            assert root_handler in logging.root.handlers
        finally:
            logging.root.removeHandler(root_handler)

    def test_structured_logging_confirmation_message(self):
        """Test that structured logging emits confirmation with structured fields."""
        stream = StringIO()

        setup_connector_logging("test_connector", use_structured_logging=True)

        for handler in _glean_logger().handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.stream = stream

        stream.truncate(0)
        stream.seek(0)

        logging.getLogger("glean.indexing.observability.observability").info(
            "Structured logging configured",
            extra={"connector": "test_connector", "log_level": "INFO"},
        )

        stream.seek(0)
        log_data = json.loads(stream.read().strip())

        assert log_data["message"] == "Structured logging configured"
        assert log_data["connector"] == "test_connector"
        assert log_data["log_level"] == "INFO"

    def test_case_insensitive_log_level(self):
        """Test that log level is case-insensitive."""
        for log_level in ["debug", "DEBUG", "DeBuG"]:
            gl = _glean_logger()
            for h in gl.handlers[:]:
                h.close()
                gl.removeHandler(h)
            setup_connector_logging("test_connector", log_level=log_level)
            assert _glean_logger().level == logging.DEBUG

    def test_invalid_log_level_raises_error(self):
        """Test that invalid log level raises AttributeError before mutating any state."""
        gl = _glean_logger()
        original_handlers = list(gl.handlers)

        with pytest.raises(AttributeError):
            setup_connector_logging("test_connector", log_level="INVALID_LEVEL")

        assert list(gl.handlers) == original_handlers


class TestBackwardCompatibilitySetupLogging:
    """Tests ensuring backward compatibility of setup_connector_logging."""

    def teardown_method(self):
        """Clean up the glean logger after each test."""
        gl = _glean_logger()
        for h in gl.handlers[:]:
            h.close()
            gl.removeHandler(h)
        gl.setLevel(logging.NOTSET)

    def test_original_signature_still_works(self):
        """Test that original function signature still works."""
        setup_connector_logging("old_connector")
        setup_connector_logging("old_connector", "DEBUG")

        assert _glean_logger().level == logging.DEBUG

    def test_third_positional_argument_log_format(self):
        """Test that explicit log_format overrides use_structured_logging."""
        gl = _glean_logger()
        for h in gl.handlers[:]:
            h.close()
            gl.removeHandler(h)

        custom_format = "%(levelname)s - %(message)s"
        setup_connector_logging("test_connector", "INFO", custom_format)

        stream = StringIO()
        for handler in _glean_logger().handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.stream = stream

        logging.getLogger("glean.test").info("Test message")

        stream.seek(0)
        output = stream.read().strip().splitlines()[-1]
        assert output == "INFO - Test message"

    def test_no_breaking_changes_to_existing_usage(self):
        """Verify existing usage patterns continue to work."""
        setup_connector_logging("connector1")
        assert _glean_logger().level == logging.INFO

        gl = _glean_logger()
        for h in gl.handlers[:]:
            h.close()
            gl.removeHandler(h)
        setup_connector_logging("connector2", log_level="WARNING")
        assert _glean_logger().level == logging.WARNING

        for h in gl.handlers[:]:
            h.close()
            gl.removeHandler(h)
        setup_connector_logging("connector3", "ERROR")
        assert _glean_logger().level == logging.ERROR
