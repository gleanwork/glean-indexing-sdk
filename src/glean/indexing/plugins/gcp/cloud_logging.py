"""GCP Cloud Logging provider for connector logging."""

import logging
from typing import Optional

from glean.indexing.observability.logging import LoggerProvider


class CloudLoggingProvider(LoggerProvider):
    """GCP Cloud Logging provider."""

    def __init__(
        self,
        project_id: str,
        log_name: str = "glean-connector",
        resource_type: str = "global",
        resource_labels: Optional[dict[str, str]] = None,
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
        self.client = cloud_logging.Client(project=project_id)
        self.logger = self.client.logger(log_name)
        self.resource_type = resource_type
        self.resource_labels = resource_labels or {}

    def setup_handler(self, logger_name: str, level: int = logging.INFO) -> logging.Handler:
        """Create Cloud Logging handler."""
        from google.cloud.logging.handlers import CloudLoggingHandler

        handler = CloudLoggingHandler(
            client=self.client,
            name=logger_name,
        )
        handler.setLevel(level)
        return handler

    def flush(self) -> None:
        """Flush any buffered logs."""
        pass
