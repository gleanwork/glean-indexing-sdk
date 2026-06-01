"""Metrics provider interface and implementations for connector observability.

Example - Custom Provider Implementation:
    ```python
    from glean.indexing.observability import MetricsProvider, MetricType

    class DataDogMetricsProvider(MetricsProvider):
        def __init__(self, api_key: str):
            from datadog import initialize, statsd
            initialize(api_key=api_key)
            self.statsd = statsd

        def emit_metric(self, name, value, metric_type=MetricType.GAUGE, labels=None):
            tags = [f"{k}:{v}" for k, v in (labels or {}).items()]
            if metric_type == MetricType.COUNTER:
                self.statsd.increment(name, value, tags=tags)
            elif metric_type == MetricType.GAUGE:
                self.statsd.gauge(name, value, tags=tags)
            elif metric_type == MetricType.HISTOGRAM:
                self.statsd.histogram(name, value, tags=tags)

        def flush(self):
            pass

    # Usage
    from glean.indexing.observability import ConnectorObservability

    provider = DataDogMetricsProvider(api_key="your-key")
    obs = ConnectorObservability("my_connector", metrics_provider=provider)
    obs.record_upload_batch_size(100)
    ```
"""

from abc import ABC, abstractmethod
from collections import defaultdict
from enum import Enum
from typing import Any, Dict, Optional


class MetricType(Enum):
    """Metric type enumeration."""

    GAUGE = "gauge"
    COUNTER = "counter"
    HISTOGRAM = "histogram"


class MetricsProvider(ABC):
    """Abstract interface for metrics emission backends.

    Allows SDK users to implement custom providers for their observability platform
    (DataDog, Prometheus, New Relic, CloudWatch, etc.).

    Example:
        ```python
        class PrometheusMetricsProvider(MetricsProvider):
            def __init__(self, registry):
                from prometheus_client import Counter, Gauge, Histogram
                self.registry = registry
                self.metrics = {}

            def emit_metric(self, name, value, metric_type=MetricType.GAUGE, labels=None):
                label_names = list(labels.keys()) if labels else []

                if name not in self.metrics:
                    if metric_type == MetricType.COUNTER:
                        self.metrics[name] = Counter(name, "", label_names, registry=self.registry)
                    elif metric_type == MetricType.GAUGE:
                        self.metrics[name] = Gauge(name, "", label_names, registry=self.registry)
                    elif metric_type == MetricType.HISTOGRAM:
                        self.metrics[name] = Histogram(name, "", label_names, registry=self.registry)

                metric = self.metrics[name]
                if labels:
                    metric = metric.labels(**labels)

                if metric_type == MetricType.COUNTER:
                    metric.inc(value)
                elif metric_type == MetricType.GAUGE:
                    metric.set(value)
                elif metric_type == MetricType.HISTOGRAM:
                    metric.observe(value)

            def flush(self):
                pass
        ```
    """

    @abstractmethod
    def emit_metric(
        self,
        name: str,
        value: float,
        metric_type: MetricType = MetricType.GAUGE,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Emit a single metric.

        Args:
            name: Metric name (e.g., "upload_batch_size")
            value: Metric value
            metric_type: Type of metric (gauge, counter, histogram)
            labels: Optional labels/tags for the metric
        """
        pass

    @abstractmethod
    def flush(self) -> None:
        """Flush any buffered metrics."""
        pass


class InMemoryMetricsProvider(MetricsProvider):
    """Default in-memory metrics provider (zero-config).

    Stores metrics in memory for later retrieval via get_metrics().
    Maintains backward compatibility with existing ConnectorObservability behavior.
    """

    def __init__(self):
        self.metrics: Dict[str, Any] = defaultdict(int)
        self.metric_history: list = []

    def emit_metric(
        self,
        name: str,
        value: float,
        metric_type: MetricType = MetricType.GAUGE,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Store metric in memory."""
        if metric_type == MetricType.COUNTER:
            self.metrics[name] += value
        else:
            self.metrics[name] = value

        self.metric_history.append(
            {
                "name": name,
                "value": value,
                "type": metric_type.value,
                "labels": labels or {},
            }
        )

    def flush(self) -> None:
        """No-op for in-memory provider."""
        pass

    def get_metrics(self) -> Dict[str, Any]:
        """Get all stored metrics."""
        return dict(self.metrics)

    def get_metric_history(self) -> list:
        """Get full history of emitted metrics."""
        return list(self.metric_history)
