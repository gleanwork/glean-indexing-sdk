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


class TestSetupConnectorLogging:
    """Tests for setup_connector_logging configuration function."""

    def teardown_method(self):
        """Clean up logging configuration after each test."""
        logging.root.handlers = []
        logging.root.setLevel(logging.WARNING)

    def test_default_configuration(self):
        """Test default human-readable logging configuration."""
        setup_connector_logging("test_connector")

        logger = logging.getLogger("test_module")
        assert logger.level == logging.NOTSET
        assert logging.root.level == logging.INFO
        assert len(logging.root.handlers) > 0

        stream = StringIO()
        for handler in logging.root.handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.stream = stream

        logger.info("Test message")

        stream.seek(0)
        output = stream.read()
        assert "test_connector" in output or "Test message" in output

    def test_structured_logging_enabled(self):
        """Test enabling structured JSON logging."""
        setup_connector_logging("test_connector", use_structured_logging=True)

        stream = StringIO()
        for handler in logging.root.handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.stream = stream

        logger = logging.getLogger("test_module")
        logger.info("Test structured message", extra={"custom_field": "custom_value"})

        stream.seek(0)
        output = stream.read().strip()
        log_data = json.loads(output)

        assert log_data["message"] == "Test structured message"
        assert log_data["level"] == "INFO"
        assert log_data["custom_field"] == "custom_value"
        assert "timestamp" in log_data

    def test_custom_log_level(self):
        """Test setting custom log level."""
        setup_connector_logging("test_connector", log_level="DEBUG")

        assert logging.root.level == logging.DEBUG

        stream = StringIO()
        for handler in logging.root.handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.stream = stream

        logger = logging.getLogger("test_module")
        logger.debug("Debug message")

        stream.seek(0)
        output = stream.read()
        assert "Debug message" in output

    def test_custom_formatter(self):
        """Test using a custom formatter."""
        custom_formatter = CompactStructuredFormatter()
        setup_connector_logging("test_connector", formatter=custom_formatter)

        stream = StringIO()
        for handler in logging.root.handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.stream = stream
                assert isinstance(handler.formatter, CompactStructuredFormatter)

        logger = logging.getLogger("test_module")
        logger.info("Test", extra={"keep": "value", "omit": ""})

        stream.seek(0)
        log_data = json.loads(stream.read().strip())
        assert "keep" in log_data
        assert "omit" not in log_data

    def test_extra_handlers(self):
        """Test adding extra handlers."""
        extra_stream = StringIO()
        extra_handler = logging.StreamHandler(extra_stream)

        setup_connector_logging("test_connector", extra_handlers=[extra_handler])

        assert len(logging.root.handlers) >= 2

        logger = logging.getLogger("test_module")
        logger.info("Test message")

        extra_stream.seek(0)
        output = extra_stream.read()
        assert "Test message" in output

    def test_structured_logging_with_extra_handlers(self):
        """Test structured logging with multiple handlers."""
        extra_stream = StringIO()
        extra_handler = logging.StreamHandler(extra_stream)

        setup_connector_logging(
            "test_connector",
            use_structured_logging=True,
            extra_handlers=[extra_handler],
        )

        for handler in logging.root.handlers:
            assert isinstance(handler.formatter, StructuredFormatter)

        extra_stream.truncate(0)
        extra_stream.seek(0)

        logger = logging.getLogger("test_module")
        logger.info("Test")

        extra_stream.seek(0)
        log_data = json.loads(extra_stream.read().strip())
        assert log_data["message"] == "Test"

    def test_force_reconfiguration(self):
        """Test that setup_connector_logging overrides existing configuration."""
        logging.basicConfig(level=logging.ERROR)
        initial_level = logging.root.level

        setup_connector_logging("test_connector", log_level="INFO")

        assert logging.root.level == logging.INFO
        assert logging.root.level != initial_level

    def test_structured_logging_confirmation_message(self):
        """Test that structured logging emits confirmation with structured fields."""
        stream = StringIO()

        setup_connector_logging("test_connector", use_structured_logging=True)

        for handler in logging.root.handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.stream = stream

        stream.truncate(0)
        stream.seek(0)

        logger = logging.getLogger("glean.indexing.observability.observability")
        logger.info(
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
        test_cases = ["debug", "DEBUG", "DeBuG"]

        for log_level in test_cases:
            logging.root.handlers = []
            setup_connector_logging("test_connector", log_level=log_level)
            assert logging.root.level == logging.DEBUG

    def test_invalid_log_level_raises_error(self):
        """Test that invalid log level raises AttributeError."""
        with pytest.raises(AttributeError):
            setup_connector_logging("test_connector", log_level="INVALID_LEVEL")


class TestBackwardCompatibilitySetupLogging:
    """Tests ensuring backward compatibility of setup_connector_logging."""

    def teardown_method(self):
        """Clean up logging configuration after each test."""
        logging.root.handlers = []
        logging.root.setLevel(logging.WARNING)

    def test_original_signature_still_works(self):
        """Test that original function signature still works."""
        setup_connector_logging("old_connector")
        setup_connector_logging("old_connector", "DEBUG")

        assert logging.root.level == logging.DEBUG

    def test_third_positional_argument_log_format(self):
        """Test that 3rd positional argument (log_format) works for backward compatibility."""
        logging.root.handlers = []

        custom_format = "%(levelname)s - %(message)s"
        setup_connector_logging("test_connector", "INFO", custom_format)

        stream = StringIO()
        for handler in logging.root.handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.stream = stream

        logger = logging.getLogger("test")
        logger.info("Test message")

        stream.seek(0)
        output = stream.read().strip()
        assert output == "INFO - Test message"

    def test_default_is_human_readable(self):
        """Test that default logging is NOT structured (backward compatible)."""
        setup_connector_logging("test_connector")

        stream = StringIO()
        for handler in logging.root.handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.stream = stream

        logger = logging.getLogger("test")
        logger.info("Test")

        stream.seek(0)
        output = stream.read()

        with pytest.raises(json.JSONDecodeError):
            json.loads(output)

    def test_no_breaking_changes_to_existing_usage(self):
        """Verify existing usage patterns continue to work."""
        setup_connector_logging("connector1")
        assert logging.root.level == logging.INFO

        logging.root.handlers = []
        setup_connector_logging("connector2", log_level="WARNING")
        assert logging.root.level == logging.WARNING

        logging.root.handlers = []
        setup_connector_logging("connector3", "ERROR")
        assert logging.root.level == logging.ERROR
