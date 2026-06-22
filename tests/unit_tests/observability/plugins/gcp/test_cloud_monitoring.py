"""Tests for Cloud Monitoring provider."""

import pytest

pytest.importorskip("google.cloud.monitoring_v3")

from unittest.mock import MagicMock, patch  # noqa: E402

from glean.indexing.observability.plugins.gcp import CloudMonitoringProvider  # noqa: E402


class TestCloudMonitoringProvider:
    """Tests for CloudMonitoringProvider."""

    @patch("google.cloud.monitoring_v3.MetricServiceClient")
    def test_initialization(self, mock_client_class):
        """Test provider initialization."""
        provider = CloudMonitoringProvider(
            project_id="test-project",
            resource_type="gce_instance",
            resource_labels={"zone": "us-central1-a"},
        )

        assert provider.project_id == "test-project"
        assert provider.project_name == "projects/test-project"
        assert provider.buffer_size == 200
        mock_client_class.assert_called_once()

    @patch("google.cloud.monitoring_v3.MetricServiceClient")
    @patch("google.cloud.monitoring_v3.MonitoredResource")
    @patch("google.cloud.monitoring_v3.TimeSeries")
    @patch("google.cloud.monitoring_v3.Point")
    def test_emit_metric(self, mock_point_class, mock_series_class, mock_resource_class, mock_client_class):
        """Test emitting a metric."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        provider = CloudMonitoringProvider(project_id="test-project")
        provider.emit_metric("test_metric", 42.0)

        assert len(provider.buffer) == 1

    @patch("google.cloud.monitoring_v3.MetricServiceClient")
    def test_emit_metric_with_labels(self, mock_client_class):
        """Test emitting metrics with labels."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        provider = CloudMonitoringProvider(project_id="test-project")
        labels = {"endpoint": "/api/test", "method": "GET"}
        provider.emit_metric("api_latency", 200.0, labels=labels)

        assert len(provider.buffer) == 1

    @patch("google.cloud.monitoring_v3.MetricServiceClient")
    def test_auto_flush_when_buffer_full(self, mock_client_class):
        """Test that metrics are auto-flushed when buffer is full."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        provider = CloudMonitoringProvider(project_id="test-project", buffer_size=3)

        provider.emit_metric("metric1", 1.0)
        provider.emit_metric("metric2", 2.0)
        mock_client.create_time_series.assert_not_called()

        provider.emit_metric("metric3", 3.0)
        mock_client.create_time_series.assert_called_once()
        assert len(provider.buffer) == 0

    @patch("google.cloud.monitoring_v3.MetricServiceClient")
    def test_manual_flush(self, mock_client_class):
        """Test manual flush of buffered metrics."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        provider = CloudMonitoringProvider(project_id="test-project")
        provider.emit_metric("metric1", 10.0)
        provider.emit_metric("metric2", 20.0)

        provider.flush()

        mock_client.create_time_series.assert_called_once()
        call_args = mock_client.create_time_series.call_args
        assert call_args.kwargs["name"] == "projects/test-project"
        assert len(call_args.kwargs["time_series"]) == 2
        assert len(provider.buffer) == 0

    @patch("google.cloud.monitoring_v3.MetricServiceClient")
    def test_flush_empty_buffer_is_noop(self, mock_client_class):
        """Test that flushing empty buffer is a no-op."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        provider = CloudMonitoringProvider(project_id="test-project")
        provider.flush()

        mock_client.create_time_series.assert_not_called()

    @patch("google.cloud.monitoring_v3.MetricServiceClient")
    def test_custom_namespace_in_metric_type(self, mock_client_class):
        """Test that metrics use custom.googleapis.com namespace."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        provider = CloudMonitoringProvider(project_id="test-project")
        provider.emit_metric("test_metric", 10.0)

        assert len(provider.buffer) == 1
        assert provider.buffer[0].metric.type == "custom.googleapis.com/test_metric"

    @patch("google.cloud.monitoring_v3.MetricServiceClient")
    def test_resource_configuration(self, mock_client_class):
        """Test that resource type and labels are configured correctly."""
        provider = CloudMonitoringProvider(
            project_id="test-project",
            resource_type="k8s_pod",
            resource_labels={"cluster_name": "prod-cluster", "namespace": "default"},
        )

        assert provider.resource.type == "k8s_pod"
        assert provider.resource.labels["cluster_name"] == "prod-cluster"
        assert provider.resource.labels["namespace"] == "default"
