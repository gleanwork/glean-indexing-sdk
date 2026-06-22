"""Custom metrics provider recipes for Prometheus, DataDog, and CloudWatch."""

from typing import Any

from glean.indexing.observability import ConnectorObservability, MetricType, MetricsProvider


class PrometheusMetricsProvider(MetricsProvider):
    """Prometheus metrics provider using prometheus_client."""

    def __init__(self, registry: Any = None) -> None:
        from prometheus_client import REGISTRY, Counter, Gauge, Histogram

        self.registry = registry or REGISTRY
        self.metrics: dict[str, Any] = {}
        self.Counter = Counter
        self.Gauge = Gauge
        self.Histogram = Histogram

    def emit_metric(
        self, name: str, value: float, metric_type: MetricType = MetricType.GAUGE, labels: dict[str, str] | None = None
    ) -> None:
        labels = labels or {}
        label_names = sorted(labels.keys())

        if name not in self.metrics:
            if metric_type == MetricType.COUNTER:
                self.metrics[name] = self.Counter(name, "", label_names, registry=self.registry)
            elif metric_type == MetricType.GAUGE:
                self.metrics[name] = self.Gauge(name, "", label_names, registry=self.registry)
            elif metric_type == MetricType.HISTOGRAM:
                self.metrics[name] = self.Histogram(name, "", label_names, registry=self.registry)

        metric = self.metrics[name]
        if labels:
            metric = metric.labels(**labels)

        if metric_type == MetricType.COUNTER:
            metric.inc(value)
        elif metric_type == MetricType.GAUGE:
            metric.set(value)
        elif metric_type == MetricType.HISTOGRAM:
            metric.observe(value)

    def flush(self) -> None:
        pass


class DataDogMetricsProvider(MetricsProvider):
    """DataDog metrics provider using datadog library."""

    def __init__(self, api_key: str) -> None:
        from datadog import initialize, statsd

        initialize(api_key=api_key)
        self.statsd = statsd

    def emit_metric(
        self, name: str, value: float, metric_type: MetricType = MetricType.GAUGE, labels: dict[str, str] | None = None
    ) -> None:
        tags = [f"{k}:{v}" for k, v in (labels or {}).items()]

        if metric_type == MetricType.COUNTER:
            self.statsd.increment(name, value, tags=tags)
        elif metric_type == MetricType.GAUGE:
            self.statsd.gauge(name, value, tags=tags)
        elif metric_type == MetricType.HISTOGRAM:
            self.statsd.histogram(name, value, tags=tags)

    def flush(self) -> None:
        pass


class CloudWatchMetricsProvider(MetricsProvider):
    """AWS CloudWatch metrics provider using boto3."""

    def __init__(self, namespace: str, region_name: str = "us-east-1") -> None:
        import boto3

        self.namespace = namespace
        self.client = boto3.client("cloudwatch", region_name=region_name)
        self.buffer: list[dict[str, Any]] = []
        self.buffer_size = 20

    def emit_metric(
        self, name: str, value: float, metric_type: MetricType = MetricType.GAUGE, labels: dict[str, str] | None = None
    ) -> None:
        dimensions = [{"Name": k, "Value": v} for k, v in (labels or {}).items()]

        unit = "None"
        if metric_type == MetricType.COUNTER:
            unit = "Count"

        metric_data = {
            "MetricName": name,
            "Value": value,
            "Unit": unit,
            "Dimensions": dimensions,
        }

        self.buffer.append(metric_data)

        if len(self.buffer) >= self.buffer_size:
            self.flush()

    def flush(self) -> None:
        if not self.buffer:
            return

        self.client.put_metric_data(Namespace=self.namespace, MetricData=self.buffer)
        self.buffer.clear()


def use_prometheus_metrics() -> None:
    """Use ConnectorObservability with Prometheus metrics."""
    from prometheus_client import CollectorRegistry

    registry = CollectorRegistry()
    provider = PrometheusMetricsProvider(registry=registry)

    obs = ConnectorObservability("my_connector", metrics_provider=provider)

    obs.start_execution()
    obs.record_upload_batch_size(100)
    obs.record_api_request_latency(latency_ms=250.5, endpoint="/api/users")
    obs.record_crawl_success()
    obs.end_execution()


def use_datadog_metrics() -> None:
    """Use ConnectorObservability with DataDog metrics."""
    provider = DataDogMetricsProvider(api_key="your-api-key")

    obs = ConnectorObservability(
        connector_name="salesforce_connector",
        datasource="salesforce_prod",
        metrics_provider=provider,
    )

    obs.start_execution()
    obs.record_upload_throughput(docs_per_sec=150.5)
    obs.record_api_request_count(endpoint="/api/opportunities")
    obs.end_execution()


def use_cloudwatch_metrics() -> None:
    """Use ConnectorObservability with CloudWatch metrics."""
    provider = CloudWatchMetricsProvider(namespace="GleanConnectors", region_name="us-west-2")

    obs = ConnectorObservability("jira_connector", metrics_provider=provider)

    obs.start_execution()
    obs.record_api_request_latency(latency_ms=180.0, endpoint="/rest/api/2/issue")
    obs.record_retry(operation="fetch_issues")
    obs.end_execution()


def use_in_memory_metrics() -> None:
    """Use default in-memory metrics provider."""
    from glean.indexing.observability.providers import InMemoryMetricsProvider

    provider = InMemoryMetricsProvider()
    obs = ConnectorObservability("my_connector", metrics_provider=provider)

    obs.start_execution()
    obs.record_upload_batch_size(50)
    obs.record_api_request_count(endpoint="/api/documents")
    obs.end_execution()

    metrics = provider.get_metrics()
    print(f"Metrics: {metrics}")

    history = provider.get_metric_history()
    print(f"Metric history: {history}")


if __name__ == "__main__":
    use_in_memory_metrics()
