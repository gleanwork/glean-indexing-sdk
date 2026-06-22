"""Tests for logger providers."""

import logging

import pytest

from glean.indexing.observability import (
    ConsoleLoggerProvider,
    LoggerProvider,
)


class TestConsoleLoggerProvider:
    """Tests for ConsoleLoggerProvider."""

    def test_setup_handler_creates_stream_handler(self):
        """Test that setup_handler creates a StreamHandler."""
        provider = ConsoleLoggerProvider()
        handler = provider.setup_handler("test_connector")

        assert isinstance(handler, logging.StreamHandler)

    def test_setup_handler_sets_log_level(self):
        """Test that setup_handler sets the correct log level."""
        provider = ConsoleLoggerProvider()
        handler = provider.setup_handler("test_connector", logging.DEBUG)

        assert handler.level == logging.DEBUG

    def test_setup_handler_default_log_level(self):
        """Test that default log level is INFO."""
        provider = ConsoleLoggerProvider()
        handler = provider.setup_handler("test_connector")

        assert handler.level == logging.INFO

    def test_flush_is_noop(self):
        """Test that flush is a no-op for console provider."""
        provider = ConsoleLoggerProvider()
        provider.flush()


class TestLoggerProviderInterface:
    """Tests for LoggerProvider abstract interface."""

    def test_cannot_instantiate_abstract_class(self):
        """Test that LoggerProvider cannot be instantiated directly."""
        with pytest.raises(TypeError):
            LoggerProvider()

    def test_custom_provider_implementation(self):
        """Test that custom providers can implement the interface."""

        class CustomLoggerProvider(LoggerProvider):
            def __init__(self):
                self.handlers_created = []

            def setup_handler(self, logger_name, level=logging.INFO):
                handler = logging.NullHandler()
                handler.setLevel(level)
                self.handlers_created.append(
                    {"logger_name": logger_name, "level": level, "handler": handler}
                )
                return handler

            def flush(self):
                pass

        provider = CustomLoggerProvider()
        handler = provider.setup_handler("custom_connector", logging.WARNING)

        assert len(provider.handlers_created) == 1
        assert provider.handlers_created[0]["logger_name"] == "custom_connector"
        assert provider.handlers_created[0]["level"] == logging.WARNING
        assert isinstance(handler, logging.NullHandler)

    def test_custom_provider_must_implement_setup_handler(self):
        """Test that custom providers must implement setup_handler."""

        class IncompleteProvider(LoggerProvider):
            def flush(self):
                pass

        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_custom_provider_must_implement_flush(self):
        """Test that custom providers must implement flush."""

        class IncompleteProvider(LoggerProvider):
            def setup_handler(self, logger_name, level=logging.INFO):
                return logging.NullHandler()

        with pytest.raises(TypeError):
            IncompleteProvider()
