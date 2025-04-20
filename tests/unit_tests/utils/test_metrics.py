"""Tests for the ConnectorMetrics utility."""

import logging
import time
from unittest.mock import MagicMock

from glean.indexing.utils import ConnectorMetrics


class TestConnectorMetrics:
    """Tests for the ConnectorMetrics utility."""

    def test_context_manager_timing(self):
        """Test that the context manager properly times operations."""
        # Create a mock logger
        mock_logger = MagicMock(spec=logging.Logger)

        # Use the metrics context manager
        with ConnectorMetrics("test_operation", logger=mock_logger) as metrics:
            # Sleep for a short time to ensure some duration
            time.sleep(0.1)

        # Check that the logger was called correctly
        mock_logger.info.assert_any_call("Starting test_operation")

        # Check that completion was logged
        completion_calls = [
            call
            for call in mock_logger.info.call_args_list
            if "Completed test_operation in" in call[0][0]
        ]
        assert len(completion_calls) == 1

        # Check that duration was recorded in stats
        assert "duration" in metrics.stats
        assert metrics.stats["duration"] > 0

    def test_record_metrics(self):
        """Test recording custom metrics."""
        # Create a mock logger
        mock_logger = MagicMock(spec=logging.Logger)

        # Use the metrics context manager
        with ConnectorMetrics("test_metrics", logger=mock_logger) as metrics:
            metrics.record("count", 42)
            metrics.record("status", "success")

        # Check that metrics were recorded
        assert metrics.stats["count"] == 42
        assert metrics.stats["status"] == "success"

        # Check that debug logs were generated for each metric
        mock_logger.debug.assert_any_call("Recorded metric count=42 for test_metrics")
        mock_logger.debug.assert_any_call("Recorded metric status=success for test_metrics")

        # Check that the final stats were logged
        final_stats_calls = [
            call
            for call in mock_logger.info.call_args_list
            if "Metrics for test_metrics:" in call[0][0]
        ]
        assert len(final_stats_calls) == 1

    def test_exception_handling(self):
        """Test that metrics work even when exceptions occur."""
        # Create a mock logger
        mock_logger = MagicMock(spec=logging.Logger)

        # Use the metrics context manager with an exception
        try:
            with ConnectorMetrics("test_exception", logger=mock_logger):
                raise ValueError("Test exception")
        except ValueError:
            pass  # Expected exception

        # Check that timing was still recorded and logged
        completion_calls = [
            call
            for call in mock_logger.info.call_args_list
            if "Completed test_exception in" in call[0][0]
        ]
        assert len(completion_calls) == 1
