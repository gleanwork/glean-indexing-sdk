"""Logger provider abstractions for cloud logging backends."""

import logging
from abc import ABC, abstractmethod


class LoggerProvider(ABC):
    """Abstract interface for cloud logging backends."""

    @abstractmethod
    def setup_handler(self, logger_name: str, level: int = logging.INFO) -> logging.Handler:
        """
        Create and return a configured logging handler.

        Args:
            logger_name: Name of the logger/connector
            level: Logging level (e.g., logging.INFO, logging.DEBUG)

        Returns:
            Configured logging.Handler instance
        """
        pass

    @abstractmethod
    def flush(self) -> None:
        """Flush any buffered logs to the backend."""
        pass


class ConsoleLoggerProvider(LoggerProvider):
    """Default console logging provider with no cloud dependencies."""

    def setup_handler(self, logger_name: str, level: int = logging.INFO) -> logging.Handler:
        """Create a StreamHandler for console output."""
        handler = logging.StreamHandler()
        handler.setLevel(level)
        return handler

    def flush(self) -> None:
        """No-op flush for console logging."""
        pass
