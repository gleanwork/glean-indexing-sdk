"""GCP Cloud Logging and Monitoring integration recipes."""

import logging
import uuid

from glean.indexing.observability import (
    ConnectorObservability,
    StructuredFormatter,
    setup_connector_logging,
)
from glean.indexing.observability.plugins.gcp import (
    CloudLoggingProvider,
    CloudMonitoringProvider,
)


def use_cloud_monitoring():
    """Use Cloud Monitoring for connector metrics."""
    provider = CloudMonitoringProvider(
        project_id="glean-production",
        resource_type="global",
        resource_labels={"environment": "production", "team": "data-platform"},
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


def use_cloud_logging():
    """Use Cloud Logging for structured logging."""
    logger_provider = CloudLoggingProvider(
        project_id="glean-production",
        log_name="salesforce-connector",
        resource_type="global",
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


def use_gcp_full_observability():
    """Use GCP for both metrics and logs."""
    metrics_provider = CloudMonitoringProvider(
        project_id="glean-staging",
        resource_type="k8s_pod",
        resource_labels={
            "cluster_name": "glean-connectors",
            "namespace": "production",
            "pod_name": "jira-connector-abc123",
        },
    )

    logger_provider = CloudLoggingProvider(
        project_id="glean-staging",
        log_name="jira-connector",
        resource_type="k8s_pod",
        resource_labels={
            "cluster_name": "glean-connectors",
            "namespace": "production",
        },
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


def use_cloud_monitoring_with_custom_buffer():
    """Use Cloud Monitoring with custom buffer size for high-volume metrics."""
    provider = CloudMonitoringProvider(
        project_id="glean-production",
        buffer_size=500,
    )

    obs = ConnectorObservability(
        connector_name="high_volume_connector",
        metrics_provider=provider,
    )

    obs.start_execution()

    for i in range(1000):
        obs.record_api_request_latency(100.0 + i, endpoint=f"/api/batch/{i}")

    obs.end_execution()


def use_gcp_error_tracking():
    """Use GCP for error tracking and monitoring."""
    metrics_provider = CloudMonitoringProvider(
        project_id="glean-production",
        resource_type="generic_task",
        resource_labels={
            "project_id": "glean-production",
            "location": "us-central1",
            "namespace": "connectors",
            "job": "error-tracking",
        },
    )

    logger_provider = CloudLoggingProvider(
        project_id="glean-production",
        log_name="connector-errors",
        resource_type="generic_task",
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


def use_gce_instance_monitoring():
    """Use GCP monitoring for GCE instance resources."""
    metrics_provider = CloudMonitoringProvider(
        project_id="glean-production",
        resource_type="gce_instance",
        resource_labels={
            "instance_id": "1234567890",
            "zone": "us-central1-a",
        },
    )

    logger_provider = CloudLoggingProvider(
        project_id="glean-production",
        log_name="gce-connector",
        resource_type="gce_instance",
        resource_labels={
            "instance_id": "1234567890",
            "zone": "us-central1-a",
        },
    )

    setup_connector_logging(
        "gce_connector",
        use_structured_logging=True,
        logger_provider=logger_provider,
    )

    obs = ConnectorObservability(
        connector_name="gce_connector",
        metrics_provider=metrics_provider,
    )

    obs.start_execution()
    obs.record_api_request_latency(150.0, endpoint="/api/data")
    obs.end_execution()


if __name__ == "__main__":
    print("GCP Cloud Logging and Monitoring Recipes")
    print("=" * 50)
    print("\n1. Cloud Monitoring Only")
    use_cloud_monitoring()
    print("\n2. Cloud Logging Only")
    use_cloud_logging()
    print("\n3. Full GCP Observability")
    use_gcp_full_observability()
    print("\n4. Custom Buffer Size")
    use_cloud_monitoring_with_custom_buffer()
    print("\n5. Error Tracking")
    use_gcp_error_tracking()
    print("\n6. GCE Instance Monitoring")
    use_gce_instance_monitoring()
