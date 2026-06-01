"""Tests for metrics providers."""

import pytest

from glean.indexing.observability import (
    InMemoryMetricsProvider,
    MetricsProvider,
    MetricType,
)


class TestInMemoryMetricsProvider:
    """Tests for InMemoryMetricsProvider."""

    def test_emit_gauge_metric(self):
        """Test emitting a gauge metric."""
        provider = InMemoryMetricsProvider()
        provider.emit_metric("test_gauge", 42.0, MetricType.GAUGE)

        metrics = provider.get_metrics()
        assert metrics["test_gauge"] == 42.0

    def test_emit_counter_metric(self):
        """Test emitting a counter metric."""
        provider = InMemoryMetricsProvider()
        provider.emit_metric("test_counter", 1.0, MetricType.COUNTER)
        provider.emit_metric("test_counter", 1.0, MetricType.COUNTER)

        metrics = provider.get_metrics()
        assert metrics["test_counter"] == 2.0

    def test_emit_histogram_metric(self):
        """Test emitting a histogram metric."""
        provider = InMemoryMetricsProvider()
        provider.emit_metric("test_histogram", 100.0, MetricType.HISTOGRAM)

        metrics = provider.get_metrics()
        assert metrics["test_histogram"] == 100.0

    def test_emit_metric_with_labels(self):
        """Test emitting metrics with labels."""
        provider = InMemoryMetricsProvider()
        labels = {"endpoint": "/api/users", "method": "GET"}
        provider.emit_metric("api_latency", 150.0, MetricType.HISTOGRAM, labels)

        history = provider.get_metric_history()
        assert len(history) == 1
        assert history[0]["name"] == "api_latency"
        assert history[0]["value"] == 150.0
        assert history[0]["labels"] == labels

    def test_gauge_overwrites_previous_value(self):
        """Test that gauge metrics overwrite previous values."""
        provider = InMemoryMetricsProvider()
        provider.emit_metric("memory_usage", 100.0, MetricType.GAUGE)
        provider.emit_metric("memory_usage", 200.0, MetricType.GAUGE)

        metrics = provider.get_metrics()
        assert metrics["memory_usage"] == 200.0

    def test_counter_accumulates(self):
        """Test that counter metrics accumulate."""
        provider = InMemoryMetricsProvider()
        provider.emit_metric("requests", 5.0, MetricType.COUNTER)
        provider.emit_metric("requests", 3.0, MetricType.COUNTER)
        provider.emit_metric("requests", 2.0, MetricType.COUNTER)

        metrics = provider.get_metrics()
        assert metrics["requests"] == 10.0

    def test_metric_history_tracks_all_emissions(self):
        """Test that metric history tracks all emissions."""
        provider = InMemoryMetricsProvider()
        provider.emit_metric("metric1", 10.0, MetricType.GAUGE)
        provider.emit_metric("metric2", 20.0, MetricType.COUNTER)
        provider.emit_metric("metric1", 15.0, MetricType.GAUGE)

        history = provider.get_metric_history()
        assert len(history) == 3
        assert history[0]["name"] == "metric1"
        assert history[0]["value"] == 10.0
        assert history[1]["name"] == "metric2"
        assert history[2]["name"] == "metric1"
        assert history[2]["value"] == 15.0

    def test_flush_is_noop(self):
        """Test that flush is a no-op for in-memory provider."""
        provider = InMemoryMetricsProvider()
        provider.emit_metric("test", 1.0)
        provider.flush()

        metrics = provider.get_metrics()
        assert metrics["test"] == 1.0

    def test_multiple_metrics(self):
        """Test handling multiple different metrics."""
        provider = InMemoryMetricsProvider()
        provider.emit_metric("upload_batch_size", 100.0, MetricType.HISTOGRAM)
        provider.emit_metric("upload_throughput", 50.0, MetricType.GAUGE)
        provider.emit_metric("api_request_count", 1.0, MetricType.COUNTER)

        metrics = provider.get_metrics()
        assert metrics["upload_batch_size"] == 100.0
        assert metrics["upload_throughput"] == 50.0
        assert metrics["api_request_count"] == 1.0


class TestMetricsProviderInterface:
    """Tests for MetricsProvider abstract interface."""

    def test_cannot_instantiate_abstract_class(self):
        """Test that MetricsProvider cannot be instantiated directly."""
        with pytest.raises(TypeError):
            MetricsProvider()

    def test_custom_provider_implementation(self):
        """Test that custom providers can implement the interface."""

        class CustomMetricsProvider(MetricsProvider):
            def __init__(self):
                self.emitted_metrics = []

            def emit_metric(self, name, value, metric_type=MetricType.GAUGE, labels=None):
                self.emitted_metrics.append(
                    {
                        "name": name,
                        "value": value,
                        "type": metric_type,
                        "labels": labels,
                    }
                )

            def flush(self):
                pass

        provider = CustomMetricsProvider()
        provider.emit_metric("custom_metric", 42.0, MetricType.GAUGE, {"tag": "value"})

        assert len(provider.emitted_metrics) == 1
        assert provider.emitted_metrics[0]["name"] == "custom_metric"
        assert provider.emitted_metrics[0]["value"] == 42.0
        assert provider.emitted_metrics[0]["labels"] == {"tag": "value"}


class TestMetricType:
    """Tests for MetricType enum."""

    def test_metric_type_values(self):
        """Test MetricType enum values."""
        assert MetricType.GAUGE.value == "gauge"
        assert MetricType.COUNTER.value == "counter"
        assert MetricType.HISTOGRAM.value == "histogram"

    def test_metric_type_enum_members(self):
        """Test MetricType has all expected members."""
        assert hasattr(MetricType, "GAUGE")
        assert hasattr(MetricType, "COUNTER")
        assert hasattr(MetricType, "HISTOGRAM")
