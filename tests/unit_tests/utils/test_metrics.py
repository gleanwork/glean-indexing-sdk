"""Tests for the ConnectorMetrics utility."""

import logging
import time
from unittest.mock import MagicMock

from glean.indexing.common import ConnectorMetrics


class TestConnectorMetrics:
    def test_context_manager_timing(self):
        """Test that the context manager properly times operations."""
        mock_logger = MagicMock(spec=logging.Logger)

        with ConnectorMetrics("test_operation", logger=mock_logger) as metrics:
            time.sleep(0.1)

        mock_logger.info.assert_any_call("Starting test_operation")

        completion_calls = [
            call
            for call in mock_logger.info.call_args_list
            if "Completed test_operation in" in call[0][0]
        ]
        assert len(completion_calls) == 1

        assert "duration" in metrics.stats
        assert metrics.stats["duration"] > 0

    def test_record_metrics(self):
        """Test recording custom metrics."""
        mock_logger = MagicMock(spec=logging.Logger)

        with ConnectorMetrics("test_metrics", logger=mock_logger) as metrics:
            metrics.record("count", 42)
            metrics.record("status", "success")

        assert metrics.stats["count"] == 42
        assert metrics.stats["status"] == "success"

        mock_logger.debug.assert_any_call("Recorded metric count=42 for test_metrics")
        mock_logger.debug.assert_any_call("Recorded metric status=success for test_metrics")

        final_stats_calls = [
            call
            for call in mock_logger.info.call_args_list
            if "Metrics for test_metrics:" in call[0][0]
        ]
        assert len(final_stats_calls) == 1

    def test_exception_handling(self):
        """Test that metrics work even when exceptions occur."""
        mock_logger = MagicMock(spec=logging.Logger)

        try:
            with ConnectorMetrics("test_exception", logger=mock_logger):
                raise ValueError("Test exception")
        except ValueError:
            pass

        completion_calls = [
            call
            for call in mock_logger.info.call_args_list
            if "Completed test_exception in" in call[0][0]
        ]
        assert len(completion_calls) == 1
