"""GCP Cloud Logging provider for connector logging."""

import logging

from glean.indexing.observability.logging import LoggerProvider


class CloudLoggingProvider(LoggerProvider):
    """GCP Cloud Logging provider."""

    def __init__(
        self,
        project_id: str,
        log_name: str = "glean-connector",
        resource_type: str = "global",
        resource_labels: dict[str, str] | None = None,
    ):
        """
        Initialize Cloud Logging provider.

        Args:
            project_id: GCP project ID
            log_name: Name for the logger
            resource_type: Monitored resource type
            resource_labels: Resource labels for the monitored resource
        """
        from google.cloud import logging as cloud_logging

        self.project_id = project_id
        self.log_name = log_name
        self.client = cloud_logging.Client(project=project_id)
        self.resource_type = resource_type
        self.resource_labels = resource_labels or {}

    def setup_handler(self, logger_name: str, level: int = logging.INFO) -> logging.Handler:
        from google.cloud.logging.handlers import CloudLoggingHandler
        from google.cloud.logging.resource import Resource

        resource = Resource(
            type=self.resource_type,
            labels=self.resource_labels,
        )

        handler = CloudLoggingHandler(
            client=self.client,
            name=self.log_name,
            resource=resource,
        )
        handler.setLevel(level)
        return handler

    def flush(self) -> None:
        pass
