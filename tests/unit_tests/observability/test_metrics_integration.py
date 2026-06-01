"""Tests for metrics integration with ConnectorObservability."""

import pytest

from glean.indexing.observability import (
    ConnectorObservability,
    InMemoryMetricsProvider,
    MetricsProvider,
    MetricType,
)


class TestConnectorObservabilityWithMetrics:
    """Tests for ConnectorObservability metrics integration."""

    def test_default_metrics_provider(self):
        """Test that default metrics provider is InMemoryMetricsProvider."""
        obs = ConnectorObservability("test_connector")
        assert isinstance(obs.metrics_provider, InMemoryMetricsProvider)

    def test_custom_metrics_provider(self):
        """Test using a custom metrics provider."""

        class CustomProvider(MetricsProvider):
            def __init__(self):
                self.metrics = []

            def emit_metric(self, name, value, metric_type=MetricType.GAUGE, labels=None):
                self.metrics.append((name, value, metric_type, labels))

            def flush(self):
                pass

        custom_provider = CustomProvider()
        obs = ConnectorObservability("test_connector", metrics_provider=custom_provider)

        assert obs.metrics_provider is custom_provider

    def test_record_upload_batch_size(self):
        """Test recording upload batch size."""
        obs = ConnectorObservability("test_connector", datasource="test_ds")
        obs.record_upload_batch_size(100)

        provider = obs.metrics_provider
        history = provider.get_metric_history()

        assert len(history) == 1
        assert history[0]["name"] == "upload_batch_size"
        assert history[0]["value"] == 100.0
        assert history[0]["type"] == "histogram"
        assert history[0]["labels"]["connector"] == "test_connector"
        assert history[0]["labels"]["datasource"] == "test_ds"

    def test_record_upload_throughput(self):
        """Test recording upload throughput."""
        obs = ConnectorObservability("test_connector")
        obs.record_upload_throughput(50.5)

        provider = obs.metrics_provider
        history = provider.get_metric_history()

        assert len(history) == 1
        assert history[0]["name"] == "upload_throughput"
        assert history[0]["value"] == 50.5
        assert history[0]["type"] == "gauge"

    def test_record_api_request_latency(self):
        """Test recording API request latency."""
        obs = ConnectorObservability("test_connector")
        obs.record_api_request_latency(150.5, "/api/users")

        provider = obs.metrics_provider
        history = provider.get_metric_history()

        assert len(history) == 1
        assert history[0]["name"] == "api_request_latency_ms"
        assert history[0]["value"] == 150.5
        assert history[0]["type"] == "histogram"
        assert history[0]["labels"]["endpoint"] == "/api/users"

    def test_record_api_request_count(self):
        """Test recording API request count."""
        obs = ConnectorObservability("test_connector")
        obs.record_api_request_count("/api/documents")
        obs.record_api_request_count("/api/documents")

        provider = obs.metrics_provider
        metrics = provider.get_metrics()

        assert metrics["api_request_count"] == 2.0

    def test_record_api_request_error(self):
        """Test recording API request errors."""
        obs = ConnectorObservability("test_connector")
        obs.record_api_request_error("/api/upload", "TimeoutError")

        provider = obs.metrics_provider
        history = provider.get_metric_history()

        assert len(history) == 1
        assert history[0]["name"] == "api_request_errors"
        assert history[0]["labels"]["endpoint"] == "/api/upload"
        assert history[0]["labels"]["error_type"] == "TimeoutError"

    def test_record_retry(self):
        """Test recording retry attempts."""
        obs = ConnectorObservability("test_connector")
        obs.record_retry("api_call")
        obs.record_retry("api_call")

        provider = obs.metrics_provider
        metrics = provider.get_metrics()

        assert metrics["retry_count"] == 2.0

    def test_record_crawl_success(self):
        """Test recording crawl success."""
        obs = ConnectorObservability("test_connector", crawl_mode="full")
        obs.record_crawl_success()

        provider = obs.metrics_provider
        history = provider.get_metric_history()

        assert len(history) == 1
        assert history[0]["name"] == "crawl_success"
        assert history[0]["value"] == 1.0
        assert history[0]["labels"]["crawl_mode"] == "full"

    def test_record_crawl_failure(self):
        """Test recording crawl failure."""
        obs = ConnectorObservability("test_connector", crawl_mode="incremental")
        obs.record_crawl_failure("NetworkError")

        provider = obs.metrics_provider
        history = provider.get_metric_history()

        assert len(history) == 1
        assert history[0]["name"] == "crawl_failure"
        assert history[0]["value"] == 1.0
        assert history[0]["labels"]["error_type"] == "NetworkError"
        assert history[0]["labels"]["crawl_mode"] == "incremental"

    def test_flush_called_on_end_execution(self):
        """Test that flush is called when execution ends."""

        class FlushTrackingProvider(MetricsProvider):
            def __init__(self):
                self.flush_called = False

            def emit_metric(self, name, value, metric_type=MetricType.GAUGE, labels=None):
                pass

            def flush(self):
                self.flush_called = True

        provider = FlushTrackingProvider()
        obs = ConnectorObservability("test_connector", metrics_provider=provider)

        obs.start_execution()
        obs.end_execution()

        assert provider.flush_called

    def test_multiple_metrics_in_lifecycle(self):
        """Test emitting multiple metrics during connector lifecycle."""
        obs = ConnectorObservability("test_connector", datasource="test_ds", crawl_mode="full")

        obs.start_execution()
        obs.record_api_request_count("/api/fetch")
        obs.record_api_request_latency(200.0, "/api/fetch")
        obs.record_upload_batch_size(50)
        obs.record_upload_throughput(25.5)
        obs.record_crawl_success()
        obs.end_execution()

        provider = obs.metrics_provider
        history = provider.get_metric_history()

        assert len(history) == 5
        metric_names = [h["name"] for h in history]
        assert "api_request_count" in metric_names
        assert "api_request_latency_ms" in metric_names
        assert "upload_batch_size" in metric_names
        assert "upload_throughput" in metric_names
        assert "crawl_success" in metric_names

    def test_metrics_labels_include_connector_context(self):
        """Test that all metrics include connector context in labels."""
        obs = ConnectorObservability(
            connector_name="my_connector",
            datasource="my_datasource",
            crawl_mode="incremental",
        )

        obs.record_upload_batch_size(100)
        obs.record_api_request_count("/api/test")

        provider = obs.metrics_provider
        history = provider.get_metric_history()

        for metric in history:
            assert "connector" in metric["labels"]
            assert metric["labels"]["connector"] == "my_connector"
            assert "datasource" in metric["labels"]
            assert metric["labels"]["datasource"] == "my_datasource"


class TestBackwardCompatibilityWithMetrics:
    """Tests ensuring backward compatibility with metrics."""

    def test_existing_metrics_dict_still_works(self):
        """Test that existing metrics dict behavior is unchanged."""
        obs = ConnectorObservability("test_connector")

        obs.record_metric("custom_metric", 123)
        obs.increment_counter("counter", 5)

        summary = obs.get_metrics_summary()
        assert summary["custom_metric"] == 123
        assert summary["counter"] == 5

    def test_metrics_provider_independent_of_metrics_dict(self):
        """Test that MetricsProvider and metrics dict are independent."""
        obs = ConnectorObservability("test_connector")

        obs.record_metric("dict_metric", 100)
        obs.record_upload_batch_size(50)

        metrics_dict = obs.get_metrics_summary()
        provider_history = obs.metrics_provider.get_metric_history()

        assert "dict_metric" in metrics_dict
        assert metrics_dict["dict_metric"] == 100

        assert len(provider_history) == 1
        assert provider_history[0]["name"] == "upload_batch_size"

    def test_default_zero_config_behavior(self):
        """Test that default behavior works without any configuration."""
        obs = ConnectorObservability("test_connector")

        obs.start_execution()
        obs.record_upload_batch_size(100)
        obs.end_execution()

        assert isinstance(obs.metrics_provider, InMemoryMetricsProvider)
        provider_metrics = obs.metrics_provider.get_metrics()
        assert provider_metrics["upload_batch_size"] == 100.0
