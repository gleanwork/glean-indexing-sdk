"""Tests for CloudWatch metrics provider."""

import pytest

pytest.importorskip("boto3")

from unittest.mock import MagicMock, patch  # noqa: E402

from glean.indexing.observability import MetricType  # noqa: E402
from glean.indexing.observability.plugins.aws import CloudWatchMetricsProvider  # noqa: E402


class TestCloudWatchMetricsProvider:
    """Tests for CloudWatchMetricsProvider."""

    @patch("boto3.client")
    def test_initialization(self, mock_boto_client):
        """Test provider initialization."""
        provider = CloudWatchMetricsProvider(
            namespace="GleanConnectors",
            region_name="us-west-2",
            dimensions={"environment": "test"},
        )

        assert provider.namespace == "GleanConnectors"
        assert provider.default_dimensions == {"environment": "test"}
        assert provider.buffer_size == 20
        mock_boto_client.assert_called_once_with("cloudwatch", region_name="us-west-2")

    @patch("boto3.client")
    def test_emit_gauge_metric(self, mock_boto_client):
        """Test emitting a gauge metric."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        provider = CloudWatchMetricsProvider(namespace="TestNamespace")
        provider.emit_metric("test_metric", 42.0, MetricType.GAUGE)

        assert len(provider.buffer) == 1
        assert provider.buffer[0]["MetricName"] == "test_metric"
        assert provider.buffer[0]["Value"] == 42.0
        assert provider.buffer[0]["Unit"] == "None"

    @patch("boto3.client")
    def test_emit_counter_metric(self, mock_boto_client):
        """Test emitting a counter metric."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        provider = CloudWatchMetricsProvider(namespace="TestNamespace")
        provider.emit_metric("test_counter", 1.0, MetricType.COUNTER)

        assert len(provider.buffer) == 1
        assert provider.buffer[0]["Unit"] == "Count"

    @patch("boto3.client")
    def test_emit_histogram_metric(self, mock_boto_client):
        """Test emitting a histogram metric."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        provider = CloudWatchMetricsProvider(namespace="TestNamespace")
        provider.emit_metric("test_histogram", 150.0, MetricType.HISTOGRAM)

        assert len(provider.buffer) == 1
        assert provider.buffer[0]["Unit"] == "Milliseconds"

    @patch("boto3.client")
    def test_emit_metric_with_labels(self, mock_boto_client):
        """Test emitting metrics with labels."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        provider = CloudWatchMetricsProvider(namespace="TestNamespace")
        labels = {"endpoint": "/api/test", "method": "GET"}
        provider.emit_metric("api_latency", 200.0, labels=labels)

        assert len(provider.buffer) == 1
        dimensions = provider.buffer[0]["Dimensions"]
        assert len(dimensions) == 2
        assert {"Name": "endpoint", "Value": "/api/test"} in dimensions
        assert {"Name": "method", "Value": "GET"} in dimensions

    @patch("boto3.client")
    def test_default_dimensions_applied(self, mock_boto_client):
        """Test that default dimensions are applied to all metrics."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        provider = CloudWatchMetricsProvider(
            namespace="TestNamespace",
            dimensions={"environment": "prod", "region": "us-east-1"},
        )
        provider.emit_metric("test_metric", 10.0)

        dimensions = provider.buffer[0]["Dimensions"]
        assert {"Name": "environment", "Value": "prod"} in dimensions
        assert {"Name": "region", "Value": "us-east-1"} in dimensions

    @patch("boto3.client")
    def test_labels_and_default_dimensions_combined(self, mock_boto_client):
        """Test that labels and default dimensions are combined."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        provider = CloudWatchMetricsProvider(
            namespace="TestNamespace",
            dimensions={"environment": "prod"},
        )
        provider.emit_metric("test_metric", 10.0, labels={"connector": "salesforce"})

        dimensions = provider.buffer[0]["Dimensions"]
        assert len(dimensions) == 2
        assert {"Name": "connector", "Value": "salesforce"} in dimensions
        assert {"Name": "environment", "Value": "prod"} in dimensions

    @patch("boto3.client")
    def test_auto_flush_when_buffer_full(self, mock_boto_client):
        """Test that metrics are auto-flushed when buffer is full."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        provider = CloudWatchMetricsProvider(namespace="TestNamespace", buffer_size=3)

        provider.emit_metric("metric1", 1.0)
        provider.emit_metric("metric2", 2.0)
        mock_client.put_metric_data.assert_not_called()

        provider.emit_metric("metric3", 3.0)
        mock_client.put_metric_data.assert_called_once()
        assert len(provider.buffer) == 0

    @patch("boto3.client")
    def test_manual_flush(self, mock_boto_client):
        """Test manual flush of buffered metrics."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        provider = CloudWatchMetricsProvider(namespace="TestNamespace")
        provider.emit_metric("metric1", 10.0)
        provider.emit_metric("metric2", 20.0)

        provider.flush()

        mock_client.put_metric_data.assert_called_once()
        call_args = mock_client.put_metric_data.call_args
        assert call_args.kwargs["Namespace"] == "TestNamespace"
        assert len(call_args.kwargs["MetricData"]) == 2
        assert len(provider.buffer) == 0

    @patch("boto3.client")
    def test_flush_empty_buffer_is_noop(self, mock_boto_client):
        """Test that flushing empty buffer is a no-op."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        provider = CloudWatchMetricsProvider(namespace="TestNamespace")
        provider.flush()

        mock_client.put_metric_data.assert_not_called()

    @patch("boto3.client")
    def test_flush_called_multiple_times(self, mock_boto_client):
        """Test that multiple flushes work correctly."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        provider = CloudWatchMetricsProvider(namespace="TestNamespace")

        provider.emit_metric("metric1", 1.0)
        provider.flush()
        assert mock_client.put_metric_data.call_count == 1

        provider.emit_metric("metric2", 2.0)
        provider.flush()
        assert mock_client.put_metric_data.call_count == 2
