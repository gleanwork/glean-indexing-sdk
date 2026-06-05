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
        point.value.double_value = value
        point.interval.end_time.seconds = int(time.time())

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
