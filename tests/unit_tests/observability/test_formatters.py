"""Tests for structured logging formatters."""

import json
import logging
from datetime import datetime
from io import StringIO

from glean.indexing.observability import (
    CompactStructuredFormatter,
    StructuredFormatter,
)


class TestStructuredFormatter:
    """Tests for StructuredFormatter."""

    def test_basic_log_formatting(self):
        """Test basic log message is formatted as JSON."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        log_data = json.loads(output)

        assert log_data["level"] == "INFO"
        assert log_data["logger"] == "test.logger"
        assert log_data["message"] == "Test message"
        assert "timestamp" in log_data

    def test_timestamp_format(self):
        """Test timestamp is in ISO 8601 format with Z suffix."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        log_data = json.loads(output)

        timestamp = log_data["timestamp"]
        assert timestamp.endswith("Z")
        # Verify it's a valid ISO format
        datetime.fromisoformat(timestamp[:-1])  # Remove Z for parsing

    def test_disable_timestamp(self):
        """Test timestamp can be disabled."""
        formatter = StructuredFormatter(include_timestamp=False)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        log_data = json.loads(output)

        assert "timestamp" not in log_data

    def test_custom_field_names(self):
        """Test custom field names can be configured."""
        formatter = StructuredFormatter(
            timestamp_field="time",
            level_field="severity",
            logger_field="source",
            message_field="text",
        )
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        log_data = json.loads(output)

        assert "time" in log_data
        assert "severity" in log_data
        assert "source" in log_data
        assert "text" in log_data
        assert log_data["severity"] == "INFO"
        assert log_data["source"] == "test"
        assert log_data["text"] == "Message"

    def test_extra_fields_from_logging_call(self):
        """Test extra fields passed via logger.info(extra={}) are included."""
        formatter = StructuredFormatter()

        # Create a logger and capture output
        logger = logging.getLogger("test.extra")
        handler = logging.StreamHandler(StringIO())
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Log with extra fields
        logger.info("Processing batch", extra={"batch_id": "123", "item_count": 50})

        # Get the formatted output
        handler.stream.seek(0)
        output = handler.stream.read()
        log_data = json.loads(output)

        assert log_data["message"] == "Processing batch"
        assert log_data["batch_id"] == "123"
        assert log_data["item_count"] == 50

    def test_extra_fields_at_formatter_level(self):
        """Test extra fields configured at formatter level are always included."""
        formatter = StructuredFormatter(
            extra_fields={"environment": "test", "version": "1.0.0"}
        )
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        log_data = json.loads(output)

        assert log_data["environment"] == "test"
        assert log_data["version"] == "1.0.0"

    def test_exception_formatting(self):
        """Test exceptions are properly formatted with traceback."""
        formatter = StructuredFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=10,
                msg="Error occurred",
                args=(),
                exc_info=True,  # This captures exception info
            )
            # Need to manually set exc_info from sys
            import sys
            record.exc_info = sys.exc_info()

            output = formatter.format(record)
            log_data = json.loads(output)

            assert "exception" in log_data
            assert log_data["exception"]["type"] == "ValueError"
            assert log_data["exception"]["message"] == "Test error"
            assert "traceback" in log_data["exception"]
            assert "ValueError: Test error" in log_data["exception"]["traceback"]

    def test_message_with_format_args(self):
        """Test log messages with formatting arguments are properly formatted."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Processing %s items in %d seconds",
            args=(100, 5),
            exc_info=None,
        )

        output = formatter.format(record)
        log_data = json.loads(output)

        assert log_data["message"] == "Processing 100 items in 5 seconds"

    def test_internal_attributes_excluded(self):
        """Test that internal LogRecord attributes are excluded from output."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="/path/to/test.py",
            lineno=42,
            msg="Message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        log_data = json.loads(output)

        # These should not appear in output
        assert "args" not in log_data
        assert "pathname" not in log_data
        assert "lineno" not in log_data
        assert "filename" not in log_data
        assert "funcName" not in log_data
        assert "process" not in log_data
        assert "thread" not in log_data

    def test_complex_object_serialization(self):
        """Test that complex objects are serialized using str()."""
        formatter = StructuredFormatter()

        # Create a record with a complex object
        class CustomObject:
            def __str__(self):
                return "custom_value"

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Message",
            args=(),
            exc_info=None,
        )
        # Add custom attribute
        record.custom_obj = CustomObject()

        # Should serialize using str()
        output = formatter.format(record)
        log_data = json.loads(output)

        assert log_data["custom_obj"] == "custom_value"

    def test_different_log_levels(self):
        """Test that different log levels are captured correctly."""
        formatter = StructuredFormatter()

        for level_name, level_num in [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
            ("ERROR", logging.ERROR),
            ("CRITICAL", logging.CRITICAL),
        ]:
            record = logging.LogRecord(
                name="test",
                level=level_num,
                pathname="test.py",
                lineno=10,
                msg=f"{level_name} message",
                args=(),
                exc_info=None,
            )

            output = formatter.format(record)
            log_data = json.loads(output)

            assert log_data["level"] == level_name
            assert log_data["message"] == f"{level_name} message"


class TestCompactStructuredFormatter:
    """Tests for CompactStructuredFormatter."""

    def test_omits_empty_values(self):
        """Test that empty/null values are omitted from output."""
        formatter = CompactStructuredFormatter()

        # Create logger with extra fields, some empty
        logger = logging.getLogger("test.compact")
        handler = logging.StreamHandler(StringIO())
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info(
            "Message",
            extra={
                "batch_id": "123",
                "empty_string": "",
                "none_value": None,
                "empty_list": [],
                "empty_dict": {},
                "valid_count": 50,
            },
        )

        handler.stream.seek(0)
        output = handler.stream.read()
        log_data = json.loads(output)

        # Should have valid fields
        assert log_data["batch_id"] == "123"
        assert log_data["valid_count"] == 50

        # Should NOT have empty fields
        assert "empty_string" not in log_data
        assert "none_value" not in log_data
        assert "empty_list" not in log_data
        assert "empty_dict" not in log_data

    def test_preserves_zero_and_false(self):
        """Test that zero and false are not considered empty."""
        formatter = CompactStructuredFormatter()

        logger = logging.getLogger("test.falsy")
        handler = logging.StreamHandler(StringIO())
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info("Message", extra={"count": 0, "flag": False})

        handler.stream.seek(0)
        output = handler.stream.read()
        log_data = json.loads(output)

        # 0 and False should be preserved
        assert log_data["count"] == 0
        assert log_data["flag"] is False

    def test_minimal_output(self):
        """Test that minimal logs produce compact output."""
        formatter = CompactStructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Done",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        log_data = json.loads(output)

        # Should only have essential fields
        assert set(log_data.keys()) == {"timestamp", "level", "logger", "message"}


class TestFormatterIntegration:
    """Integration tests for formatters with stdlib logging."""

    def test_with_stream_handler(self):
        """Test formatter works with StreamHandler."""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())

        logger = logging.getLogger("test.integration")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info("Integration test", extra={"test_id": "001"})

        stream.seek(0)
        output = stream.read()
        log_data = json.loads(output)

        assert log_data["message"] == "Integration test"
        assert log_data["test_id"] == "001"

    def test_multiple_handlers_with_different_formatters(self):
        """Test multiple handlers can use different formatters."""
        # JSON handler
        json_stream = StringIO()
        json_handler = logging.StreamHandler(json_stream)
        json_handler.setFormatter(StructuredFormatter())

        # Compact JSON handler
        compact_stream = StringIO()
        compact_handler = logging.StreamHandler(compact_stream)
        compact_handler.setFormatter(CompactStructuredFormatter())

        logger = logging.getLogger("test.multi")
        logger.addHandler(json_handler)
        logger.addHandler(compact_handler)
        logger.setLevel(logging.INFO)

        logger.info("Test", extra={"key": "value", "empty": ""})

        # Both should produce valid JSON
        json_stream.seek(0)
        json_data = json.loads(json_stream.read())

        compact_stream.seek(0)
        compact_data = json.loads(compact_stream.read())

        # Both should have the message
        assert json_data["message"] == "Test"
        assert compact_data["message"] == "Test"

        # Regular formatter includes empty field
        assert json_data.get("empty") == ""

        # Compact formatter omits empty field
        assert "empty" not in compact_data
