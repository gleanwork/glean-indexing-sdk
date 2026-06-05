"""AWS CloudWatch Metrics provider for connector metrics."""

from typing import Optional

from glean.indexing.observability import MetricsProvider, MetricType


class CloudWatchMetricsProvider(MetricsProvider):
    """AWS CloudWatch metrics provider."""

    def __init__(
        self,
        namespace: str,
        region_name: str = "us-east-1",
        dimensions: Optional[dict[str, str]] = None,
        buffer_size: int = 20,
    ):
        """
        Initialize CloudWatch metrics provider.

        Args:
            namespace: CloudWatch namespace (e.g., "GleanConnectors")
            region_name: AWS region name
            dimensions: Default dimensions to apply to all metrics
            buffer_size: Number of metrics to buffer before flushing
        """
        import boto3

        self.namespace = namespace
        self.client = boto3.client("cloudwatch", region_name=region_name)
        self.default_dimensions = dimensions or {}
        self.buffer: list[dict] = []
        self.buffer_size = buffer_size

    def emit_metric(
        self,
        name: str,
        value: float,
        metric_type: MetricType = MetricType.GAUGE,
        labels: Optional[dict[str, str]] = None,
    ) -> None:
        """Emit a metric to CloudWatch."""
        merged_dimensions = {**self.default_dimensions, **(labels or {})}
        dimensions = [{"Name": k, "Value": v} for k, v in merged_dimensions.items()]

        unit = "None"
        if metric_type == MetricType.COUNTER:
            unit = "Count"
        elif metric_type == MetricType.HISTOGRAM:
            unit = "Milliseconds"

        self.buffer.append(
            {
                "MetricName": name,
                "Value": value,
                "Unit": unit,
                "Dimensions": dimensions,
            }
        )

        if len(self.buffer) >= self.buffer_size:
            self.flush()

    def flush(self) -> None:
        """Flush buffered metrics to CloudWatch."""
        if not self.buffer:
            return

        for i in range(0, len(self.buffer), 20):
            batch = self.buffer[i : i + 20]
            self.client.put_metric_data(Namespace=self.namespace, MetricData=batch)

        self.buffer.clear()
