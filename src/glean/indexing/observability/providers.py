"""Metrics provider interface and implementations for connector observability."""

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
    (DataDog, Prometheus, New Relic, etc.).
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
