"""GCP Cloud Monitoring provider for connector metrics."""

import time
from typing import Optional

from glean.indexing.observability import MetricsProvider, MetricType


class CloudMonitoringProvider(MetricsProvider):
    """GCP Cloud Monitoring metrics provider."""

    def __init__(
        self,
        project_id: str,
        resource_type: str = "global",
        resource_labels: Optional[dict[str, str]] = None,
        buffer_size: int = 200,
    ):
        """
        Initialize Cloud Monitoring provider.

        Args:
            project_id: GCP project ID
            resource_type: Monitored resource type (e.g., "global", "gce_instance")
            resource_labels: Resource labels for the monitored resource
            buffer_size: Number of metrics to buffer before flushing
        """
        from google.cloud import monitoring_v3

        self.project_id = project_id
        self.project_name = f"projects/{project_id}"
        self.client = monitoring_v3.MetricServiceClient()
        self.resource = monitoring_v3.MonitoredResource(
            type=resource_type,
            labels=resource_labels or {},
        )
        self.buffer: list = []
        self.buffer_size = buffer_size

    def emit_metric(
        self,
        name: str,
        value: float,
        metric_type: MetricType = MetricType.GAUGE,
        labels: Optional[dict[str, str]] = None,
    ) -> None:
        """Emit a metric to Cloud Monitoring."""
        from google.cloud import monitoring_v3

        series = monitoring_v3.TimeSeries()
        series.metric.type = f"custom.googleapis.com/{name}"
        if labels:
            series.metric.labels.update(labels)
        series.resource = self.resource

        point = monitoring_v3.Point()
        now = int(time.time())
        point.interval.end_time.seconds = now

        if metric_type == MetricType.COUNTER:
            series.metric_kind = monitoring_v3.MetricDescriptor.MetricKind.CUMULATIVE
            point.value.int64_value = int(value)
            point.interval.start_time.seconds = now
        elif metric_type == MetricType.HISTOGRAM:
            series.metric_kind = monitoring_v3.MetricDescriptor.MetricKind.GAUGE
            series.value_type = monitoring_v3.MetricDescriptor.ValueType.DISTRIBUTION
            point.value.distribution_value.count = 1
            point.value.distribution_value.mean = value
            point.value.distribution_value.bucket_counts.extend([1])
        else:
            series.metric_kind = monitoring_v3.MetricDescriptor.MetricKind.GAUGE
            point.value.double_value = value

        series.points = [point]
        self.buffer.append(series)

        if len(self.buffer) >= self.buffer_size:
            self.flush()

    def flush(self) -> None:
        """Flush buffered metrics to Cloud Monitoring."""
        if not self.buffer:
            return

        self.client.create_time_series(name=self.project_name, time_series=self.buffer)
        self.buffer.clear()
