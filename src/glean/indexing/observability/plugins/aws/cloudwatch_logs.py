"""AWS CloudWatch Logs provider for connector logging."""

import logging

from glean.indexing.observability.logging import LoggerProvider


class CloudWatchLogsProvider(LoggerProvider):
    """AWS CloudWatch Logs provider."""

    def __init__(
        self,
        log_group: str,
        log_stream: str,
        region_name: str = "us-east-1",
        create_log_group: bool = True,
    ):
        """
        Initialize CloudWatch Logs provider.

        Args:
            log_group: CloudWatch log group name
            log_stream: CloudWatch log stream name
            region_name: AWS region name
            create_log_group: Whether to create log group if it doesn't exist
        """
        self.log_group = log_group
        self.log_stream = log_stream
        self.region_name = region_name
        self.create_log_group = create_log_group

    def setup_handler(self, logger_name: str, level: int = logging.INFO) -> logging.Handler:
        import boto3
        import watchtower

        boto3_client = boto3.client("logs", region_name=self.region_name)

        handler = watchtower.CloudWatchLogHandler(
            log_group=self.log_group,
            stream_name=self.log_stream,
            use_queues=True,
            send_interval=5,
            create_log_group=self.create_log_group,
            boto3_client=boto3_client,
        )
        handler.setLevel(level)
        return handler

    def flush(self) -> None:
        pass
