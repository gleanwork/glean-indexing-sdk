"""AWS CloudWatch integration recipes."""

import logging
import uuid

from glean.indexing.observability import (
    ConnectorObservability,
    StructuredFormatter,
    setup_connector_logging,
)
from glean.indexing.observability.plugins.aws import (
    CloudWatchLogsProvider,
    CloudWatchMetricsProvider,
)


def use_cloudwatch_metrics():
    """Use CloudWatch for connector metrics."""
    provider = CloudWatchMetricsProvider(
        namespace="GleanConnectors",
        region_name="us-west-2",
        dimensions={"environment": "production", "team": "data-platform"},
    )

    obs = ConnectorObservability(
        connector_name="salesforce_connector",
        datasource="salesforce_prod",
        crawl_mode="incremental",
        metrics_provider=provider,
    )

    obs.start_execution()
    obs.log_data_fetch_started()

    obs.record_upload_batch_size(100)
    obs.record_upload_throughput(50.5)
    obs.record_api_request_latency(250.0, endpoint="/api/opportunities")
    obs.record_api_request_latency(180.0, endpoint="/api/accounts")

    upload_id = str(uuid.uuid4())
    obs.log_batch_upload_started(batch_index=0, batch_count=1, batch_size=100, upload_id=upload_id)
    obs.log_batch_upload_completed(batch_index=0, batch_count=1, batch_size=100, duration_ms=500, upload_id=upload_id)

    obs.end_execution()


def use_cloudwatch_logs():
    """Use CloudWatch Logs for structured logging."""
    logger_provider = CloudWatchLogsProvider(
        log_group="/glean/connectors",
        log_stream="salesforce-connector",
        region_name="us-west-2",
    )

    setup_connector_logging(
        "salesforce_connector",
        log_level="INFO",
        use_structured_logging=True,
        logger_provider=logger_provider,
    )

    logger = logging.getLogger(__name__)
    logger.info(
        "Crawl started",
        extra={"connector": "salesforce", "crawl_mode": "full", "run_id": "abc-123"},
    )
    logger.info("Fetched 500 records from Salesforce API")
    logger.info("Crawl completed successfully")


def use_cloudwatch_full_observability():
    """Use CloudWatch for both metrics and logs."""
    metrics_provider = CloudWatchMetricsProvider(
        namespace="GleanConnectors",
        region_name="us-west-2",
        dimensions={"environment": "staging"},
    )

    logger_provider = CloudWatchLogsProvider(
        log_group="/glean/connectors",
        log_stream="jira-connector",
        region_name="us-west-2",
    )

    setup_connector_logging(
        "jira_connector",
        use_structured_logging=True,
        logger_provider=logger_provider,
    )

    obs = ConnectorObservability(
        connector_name="jira_connector",
        datasource="jira_prod",
        crawl_mode="incremental",
        metrics_provider=metrics_provider,
    )

    obs.start_execution()
    obs.log_data_fetch_started()

    obs.record_api_request_latency(120.0, endpoint="/rest/api/3/search")
    obs.record_upload_batch_size(50)

    upload_id = str(uuid.uuid4())
    obs.log_batch_upload_started(batch_index=0, batch_count=1, batch_size=50, upload_id=upload_id)
    obs.record_batch_upload_latency(350.0)
    obs.log_batch_upload_completed(batch_index=0, batch_count=1, batch_size=50, duration_ms=350, upload_id=upload_id)

    obs.end_execution()


def use_cloudwatch_with_custom_buffer():
    """Use CloudWatch with custom buffer size for high-volume metrics."""
    provider = CloudWatchMetricsProvider(
        namespace="GleanConnectors",
        region_name="us-east-1",
        buffer_size=50,
    )

    obs = ConnectorObservability(
        connector_name="high_volume_connector",
        metrics_provider=provider,
    )

    obs.start_execution()

    for i in range(100):
        obs.record_api_request_latency(100.0 + i, endpoint=f"/api/batch/{i}")

    obs.end_execution()


def use_cloudwatch_error_tracking():
    """Use CloudWatch for error tracking and monitoring."""
    metrics_provider = CloudWatchMetricsProvider(
        namespace="GleanConnectors",
        region_name="us-west-2",
    )

    logger_provider = CloudWatchLogsProvider(
        log_group="/glean/connectors/errors",
        log_stream="connector-errors",
        region_name="us-west-2",
    )

    setup_connector_logging(
        "error_tracking_connector",
        log_level="WARNING",
        use_structured_logging=True,
        logger_provider=logger_provider,
    )

    obs = ConnectorObservability(
        connector_name="error_tracking_connector",
        metrics_provider=metrics_provider,
    )

    obs.start_execution()

    try:
        raise ValueError("Simulated API error")
    except Exception as e:
        obs.fail_execution(e)

    obs.record_crawl_outcome("failed", error_message="API rate limit exceeded")


if __name__ == "__main__":
    print("AWS CloudWatch Recipes")
    print("=" * 50)
    print("\n1. CloudWatch Metrics Only")
    use_cloudwatch_metrics()
    print("\n2. CloudWatch Logs Only")
    use_cloudwatch_logs()
    print("\n3. Full CloudWatch Observability")
    use_cloudwatch_full_observability()
    print("\n4. Custom Buffer Size")
    use_cloudwatch_with_custom_buffer()
    print("\n5. Error Tracking")
    use_cloudwatch_error_tracking()
