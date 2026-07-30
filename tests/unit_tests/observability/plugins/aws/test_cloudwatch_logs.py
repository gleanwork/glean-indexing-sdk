"""Tests for CloudWatch Logs provider."""

import logging

import pytest

pytest.importorskip("watchtower")

from unittest.mock import MagicMock, patch  # noqa: E402

from glean.indexing.observability.plugins.aws import CloudWatchLogsProvider  # noqa: E402


class TestCloudWatchLogsProvider:
    """Tests for CloudWatchLogsProvider."""

    @patch("watchtower.CloudWatchLogHandler")
    def test_initialization(self, mock_handler_class):
        """Test provider initialization."""
        provider = CloudWatchLogsProvider(
            log_group="/glean/connectors",
            log_stream="test-connector",
            region_name="us-west-2",
        )

        assert provider.log_group == "/glean/connectors"
        assert provider.log_stream == "test-connector"
        assert provider.region_name == "us-west-2"
        assert provider.create_log_group is True

    @patch("boto3.client")
    @patch("watchtower.CloudWatchLogHandler")
    def test_setup_handler_creates_cloudwatch_handler(
        self, mock_handler_class, mock_boto_client
    ):
        """Test that setup_handler creates a CloudWatch handler."""
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        provider = CloudWatchLogsProvider(
            log_group="/test/logs",
            log_stream="test-stream",
            region_name="us-west-2",
        )
        handler = provider.setup_handler("test_connector")

        mock_boto_client.assert_called_once_with("logs", region_name="us-west-2")
        mock_handler_class.assert_called_once_with(
            log_group="/test/logs",
            stream_name="test-stream",
            use_queues=True,
            send_interval=5,
            create_log_group=True,
            boto3_client=mock_client,
        )
        assert handler == mock_handler

    @patch("watchtower.CloudWatchLogHandler")
    def test_setup_handler_sets_log_level(self, mock_handler_class):
        """Test that setup_handler sets the correct log level."""
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        provider = CloudWatchLogsProvider(
            log_group="/test/logs",
            log_stream="test-stream",
        )
        handler = provider.setup_handler("test_connector", logging.DEBUG)

        mock_handler.setLevel.assert_called_once_with(logging.DEBUG)

    @patch("watchtower.CloudWatchLogHandler")
    def test_setup_handler_default_log_level(self, mock_handler_class):
        """Test that default log level is INFO."""
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        provider = CloudWatchLogsProvider(
            log_group="/test/logs",
            log_stream="test-stream",
        )
        handler = provider.setup_handler("test_connector")

        mock_handler.setLevel.assert_called_once_with(logging.INFO)

    @patch("watchtower.CloudWatchLogHandler")
    def test_create_log_group_parameter(self, mock_handler_class):
        """Test create_log_group parameter is passed through."""
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        provider = CloudWatchLogsProvider(
            log_group="/test/logs",
            log_stream="test-stream",
            create_log_group=False,
        )
        provider.setup_handler("test_connector")

        call_args = mock_handler_class.call_args
        assert call_args.kwargs["create_log_group"] is False

    @patch("watchtower.CloudWatchLogHandler")
    def test_flush_is_noop(self, mock_handler_class):
        """Test that flush is a no-op."""
        provider = CloudWatchLogsProvider(
            log_group="/test/logs",
            log_stream="test-stream",
        )
        provider.flush()

    @patch("watchtower.CloudWatchLogHandler")
    def test_multiple_handlers_can_be_created(self, mock_handler_class):
        """Test that multiple handlers can be created from same provider."""
        mock_handler_class.side_effect = [MagicMock(), MagicMock()]

        provider = CloudWatchLogsProvider(
            log_group="/test/logs",
            log_stream="test-stream",
        )

        handler1 = provider.setup_handler("connector1")
        handler2 = provider.setup_handler("connector2")

        assert handler1 != handler2
        assert mock_handler_class.call_count == 2
