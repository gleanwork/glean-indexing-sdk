"""Metric recording recipes for tracking connector operations."""

import time
from typing import Any

from glean.indexing.observability import ConnectorObservability


def record_upload_metrics(documents: list[dict[str, Any]], batch_size: int = 100) -> None:
    """Record upload batch size and throughput metrics."""
    obs = ConnectorObservability("my_connector")

    start_time = time.time()
    batches = [documents[i : i + batch_size] for i in range(0, len(documents), batch_size)]

    for batch in batches:
        obs.record_upload_batch_size(len(batch))
        upload_batch(batch)

    duration = time.time() - start_time
    docs_per_sec = len(documents) / duration if duration > 0 else 0

    obs.record_upload_throughput(docs_per_sec)


def record_api_metrics(endpoint: str) -> dict[str, Any]:
    """Record API request latency and count metrics."""
    obs = ConnectorObservability("my_connector")

    start_time = time.time()

    try:
        obs.record_api_request_count(endpoint)

        response = make_api_request(endpoint)
        latency_ms = (time.time() - start_time) * 1000

        obs.record_api_request_latency(latency_ms=latency_ms, endpoint=endpoint)

        return response

    except Exception as error:
        obs.record_api_request_error(endpoint=endpoint, error_type=type(error).__name__)
        raise


def record_retry_metrics() -> list[dict[str, Any]]:
    """Record retry attempt metrics."""
    obs = ConnectorObservability("my_connector")

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            return fetch_with_retries()
        except Exception:
            if attempt < max_attempts - 1:
                obs.record_retry(operation="fetch_data")
                time.sleep(2**attempt)
            else:
                raise

    return []


def record_crawl_outcome_metrics(crawl_mode: str) -> None:
    """Record crawl success or failure metrics."""
    obs = ConnectorObservability("my_connector", crawl_mode=crawl_mode)

    try:
        obs.start_execution()
        run_crawl()
        obs.record_crawl_success()
        obs.end_execution()

    except Exception as error:
        obs.record_crawl_failure(error_type=type(error).__name__)
        obs.fail_execution(error)
        raise


def record_custom_metrics() -> None:
    """Record custom metrics using generic methods."""
    obs = ConnectorObservability("my_connector")

    obs.record_metric("api_calls_saved_by_cache", 42)
    obs.increment_counter("permission_checks")
    obs.increment_counter("permission_checks", value=5)

    obs.start_timer("database_query")
    time.sleep(0.1)
    duration = obs.end_timer("database_query")

    metrics = obs.get_metrics_summary()
    print(f"Database query duration: {duration:.3f}s")
    print(f"Permission checks: {metrics['permission_checks']}")


def record_with_labels() -> None:
    """Record metrics with custom labels via metrics provider."""
    from glean.indexing.observability import MetricType
    from glean.indexing.observability.providers import InMemoryMetricsProvider

    provider = InMemoryMetricsProvider()
    obs = ConnectorObservability("my_connector", metrics_provider=provider)

    obs.metrics_provider.emit_metric(
        name="custom_operation_duration",
        value=123.5,
        metric_type=MetricType.HISTOGRAM,
        labels={
            "connector": "salesforce",
            "datasource": "prod",
            "operation_type": "incremental_sync",
            "region": "us-west-2",
        },
    )

    history = provider.get_metric_history()
    print(f"Recorded {len(history)} metrics")


def track_all_metrics_in_crawl() -> None:
    """Comprehensive example recording all metric types during a crawl."""
    obs = ConnectorObservability(
        connector_name="comprehensive_connector",
        datasource="salesforce",
        crawl_mode="full",
    )

    try:
        obs.start_execution()

        endpoint = "/api/v1/opportunities"
        start_time = time.time()
        obs.record_api_request_count(endpoint)

        try:
            data = make_api_request(endpoint)
            latency_ms = (time.time() - start_time) * 1000
            obs.record_api_request_latency(latency_ms=latency_ms, endpoint=endpoint)
        except Exception as error:
            obs.record_api_request_error(endpoint=endpoint, error_type=type(error).__name__)
            obs.record_retry(operation="fetch_opportunities")
            raise

        documents = transform_to_documents(data)

        batch_size = 100
        batches = [documents[i : i + batch_size] for i in range(0, len(documents), batch_size)]

        upload_start = time.time()
        for batch in batches:
            obs.record_upload_batch_size(len(batch))
            upload_batch(batch)

        upload_duration = time.time() - upload_start
        docs_per_sec = len(documents) / upload_duration if upload_duration > 0 else 0
        obs.record_upload_throughput(docs_per_sec)

        obs.record_crawl_success()
        obs.end_execution()

    except Exception as error:
        obs.record_crawl_failure(error_type=type(error).__name__)
        obs.fail_execution(error)
        raise


def upload_batch(batch: list[dict[str, Any]]) -> None:
    """Upload batch to Glean."""
    time.sleep(0.05)


def make_api_request(endpoint: str) -> list[dict[str, Any]]:
    """Make API request to source system."""
    time.sleep(0.1)
    return [{"id": str(i)} for i in range(100)]


def fetch_with_retries() -> list[dict[str, Any]]:
    """Fetch data with retry logic."""
    return [{"id": "1"}]


def run_crawl() -> None:
    """Run the crawl process."""
    time.sleep(0.2)


def transform_to_documents(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Transform source data to Glean documents."""
    return [{"id": item["id"], "title": f"Document {item['id']}"} for item in data]


if __name__ == "__main__":
    from glean.indexing.observability import setup_connector_logging

    setup_connector_logging("metrics_examples", use_structured_logging=True)

    documents = [{"id": str(i), "title": f"Doc {i}"} for i in range(250)]
    record_upload_metrics(documents)
    record_custom_metrics()
    track_all_metrics_in_crawl()
