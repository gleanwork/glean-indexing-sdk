"""GCP Cloud Monitoring provider for connector metrics."""

import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from google.cloud.monitoring_v3.types import TimeSeries

from glean.indexing.observability import MetricsProvider, MetricType


class CloudMonitoringProvider(MetricsProvider):
    """GCP Cloud Monitoring metrics provider (beta).

    Requires the ``gcp`` extra: ``uv add glean-indexing-sdk[gcp]``.
    """

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
        from google.api import monitored_resource_pb2
        from google.cloud import monitoring_v3

        self.project_id = project_id
        self.project_name = f"projects/{project_id}"
        self.client = monitoring_v3.MetricServiceClient()
        self.resource = monitored_resource_pb2.MonitoredResource(
            type=resource_type,
            labels=resource_labels or {},
        )
        self.buffer: list["TimeSeries"] = []
        self.buffer_size = buffer_size

    def emit_metric(
        self,
        name: str,
        value: float,
        metric_type: MetricType = MetricType.GAUGE,
        labels: Optional[dict[str, str]] = None,
    ) -> None:
        from google.api import distribution_pb2, metric_pb2
        from google.cloud import monitoring_v3
        from google.protobuf import timestamp_pb2

        now = int(time.time())
        end_time = timestamp_pb2.Timestamp(seconds=now)
        interval = monitoring_v3.TimeInterval(end_time=end_time)

        if metric_type == MetricType.COUNTER:
            metric_kind = metric_pb2.MetricDescriptor.MetricKind.CUMULATIVE
            value_type = metric_pb2.MetricDescriptor.ValueType.INT64
            interval = monitoring_v3.TimeInterval(
                start_time=timestamp_pb2.Timestamp(seconds=now),
                end_time=end_time,
            )
            typed_value = monitoring_v3.TypedValue(int64_value=int(value))
        elif metric_type == MetricType.HISTOGRAM:
            metric_kind = metric_pb2.MetricDescriptor.MetricKind.GAUGE
            value_type = metric_pb2.MetricDescriptor.ValueType.DISTRIBUTION
            distribution = distribution_pb2.Distribution(count=1, mean=value, bucket_counts=[1])
            typed_value = monitoring_v3.TypedValue(distribution_value=distribution)
        else:
            metric_kind = metric_pb2.MetricDescriptor.MetricKind.GAUGE
            value_type = metric_pb2.MetricDescriptor.ValueType.DOUBLE
            typed_value = monitoring_v3.TypedValue(double_value=value)

        point = monitoring_v3.Point(interval=interval, value=typed_value)
        series = monitoring_v3.TimeSeries(
            metric=metric_pb2.Metric(type=f"custom.googleapis.com/{name}", labels=labels or {}),
            resource=self.resource,
            metric_kind=metric_kind,
            value_type=value_type,
            points=[point],
        )
        self.buffer.append(series)

        if len(self.buffer) >= self.buffer_size:
            self.flush()

    def flush(self) -> None:
        if not self.buffer:
            return

        self.client.create_time_series(name=self.project_name, time_series=self.buffer.copy())
        self.buffer.clear()
