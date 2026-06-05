"""Tests for Cloud Logging provider."""

import logging

import pytest

pytest.importorskip("google.cloud.logging")

from unittest.mock import MagicMock, patch

from glean.indexing.plugins.gcp import CloudLoggingProvider


class TestCloudLoggingProvider:
    """Tests for CloudLoggingProvider."""

    @patch("google.cloud.logging.Client")
    def test_initialization(self, mock_client_class):
        """Test provider initialization."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_logger = MagicMock()
        mock_client.logger.return_value = mock_logger

        provider = CloudLoggingProvider(
            project_id="test-project",
            log_name="test-connector",
            resource_type="gce_instance",
            resource_labels={"zone": "us-central1-a"},
        )

        assert provider.project_id == "test-project"
        assert provider.resource_type == "gce_instance"
        assert provider.resource_labels == {"zone": "us-central1-a"}
        mock_client_class.assert_called_once_with(project="test-project")
        mock_client.logger.assert_called_once_with("test-connector")

    @patch("google.cloud.logging.Client")
    @patch("google.cloud.logging.handlers.CloudLoggingHandler")
    def test_setup_handler_creates_cloud_logging_handler(self, mock_handler_class, mock_client_class):
        """Test that setup_handler creates a Cloud Logging handler."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        provider = CloudLoggingProvider(project_id="test-project", log_name="test-logs")
        handler = provider.setup_handler("test_connector")

        mock_handler_class.assert_called_once_with(
            client=mock_client,
            name="test_connector",
        )
        assert handler == mock_handler

    @patch("google.cloud.logging.Client")
    @patch("google.cloud.logging.handlers.CloudLoggingHandler")
    def test_setup_handler_sets_log_level(self, mock_handler_class, mock_client_class):
        """Test that setup_handler sets the correct log level."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        provider = CloudLoggingProvider(project_id="test-project")
        handler = provider.setup_handler("test_connector", logging.DEBUG)

        mock_handler.setLevel.assert_called_once_with(logging.DEBUG)

    @patch("google.cloud.logging.Client")
    @patch("google.cloud.logging.handlers.CloudLoggingHandler")
    def test_setup_handler_default_log_level(self, mock_handler_class, mock_client_class):
        """Test that default log level is INFO."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        provider = CloudLoggingProvider(project_id="test-project")
        handler = provider.setup_handler("test_connector")

        mock_handler.setLevel.assert_called_once_with(logging.INFO)

    @patch("google.cloud.logging.Client")
    def test_flush_is_noop(self, mock_client_class):
        """Test that flush is a no-op."""
        provider = CloudLoggingProvider(project_id="test-project")
        provider.flush()

    @patch("google.cloud.logging.Client")
    @patch("google.cloud.logging.handlers.CloudLoggingHandler")
    def test_multiple_handlers_can_be_created(self, mock_handler_class, mock_client_class):
        """Test that multiple handlers can be created from same provider."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_handler_class.side_effect = [MagicMock(), MagicMock()]

        provider = CloudLoggingProvider(project_id="test-project")

        handler1 = provider.setup_handler("connector1")
        handler2 = provider.setup_handler("connector2")

        assert handler1 != handler2
        assert mock_handler_class.call_count == 2

    @patch("google.cloud.logging.Client")
    def test_default_log_name(self, mock_client_class):
        """Test default log name is glean-connector."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        provider = CloudLoggingProvider(project_id="test-project")

        mock_client.logger.assert_called_once_with("glean-connector")

    @patch("google.cloud.logging.Client")
    def test_default_resource_type(self, mock_client_class):
        """Test default resource type is global."""
        provider = CloudLoggingProvider(project_id="test-project")

        assert provider.resource_type == "global"
        assert provider.resource_labels == {}
