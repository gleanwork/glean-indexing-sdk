"""Runtime smoke test for the advertised ``gcp`` optional dependency."""

from unittest.mock import patch

from google.cloud import logging_v2, monitoring_v3, secretmanager
from google.cloud.logging_v2.handlers import CloudLoggingHandler

from glean.indexing.deployment import DeploymentConfig
from glean.indexing.deployment.secrets import GCPSecretsBackend
from glean.indexing.observability import MetricType
from glean.indexing.observability.plugins.gcp import CloudLoggingProvider, CloudMonitoringProvider


def main() -> None:
    """Construct every public GCP integration without contacting Google Cloud."""
    with (
        patch.object(logging_v2, "Client"),
        patch.object(monitoring_v3, "MetricServiceClient"),
        patch.object(CloudLoggingHandler, "__init__", return_value=None),
    ):
        logging_provider = CloudLoggingProvider(project_id="test-project")
        logging_provider.setup_handler("test-connector")
        monitoring_provider = CloudMonitoringProvider(project_id="test-project")
        monitoring_provider.emit_metric("gauge", 1.5)
        monitoring_provider.emit_metric("counter", 2, MetricType.COUNTER)
        monitoring_provider.emit_metric("histogram", 3.5, MetricType.HISTOGRAM)

    config = DeploymentConfig(
        connector_name="test_connector",
        connector_class="TestConnector",
        connector_module="connectors.test",
        cloud="gcp",
        region="us-central1",
        cluster_name="test-cluster",
        project_id="test-project",
        artifact_registry_repo="us-central1-docker.pkg.dev/test-project/connectors",
    )
    secrets_backend = GCPSecretsBackend(config)
    with patch.object(secretmanager, "SecretManagerServiceClient") as client_class:
        client_class.return_value.list_secrets.return_value = []
        assert secrets_backend.list() == []

    assert logging_provider.project_id == "test-project"
    assert monitoring_provider.project_name == "projects/test-project"
    assert len(monitoring_provider.buffer) == 3


if __name__ == "__main__":
    main()
