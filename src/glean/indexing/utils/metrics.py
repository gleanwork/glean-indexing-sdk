"""Performance metrics tracking utility for connectors."""

import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ConnectorMetrics:
    """A context manager for tracking connector metrics."""

    def __init__(self, name: str, logger: Optional[logging.Logger] = None):
        """Initialize the ConnectorMetrics.

        Args:
            name: The name of the operation being timed.
            logger: An optional logger to use for metrics. If None, the default logger is used.
        """
        self.name = name
        self.logger = logger or logging.getLogger(__name__)
        self.start_time = 0
        self.end_time = 0
        self.stats: Dict[str, Any] = {}

    def __enter__(self) -> "ConnectorMetrics":
        """Enter the context manager, starting the timer.

        Returns:
            The ConnectorMetrics instance.
        """
        self.start_time = time.time()
        self.logger.info(f"Starting {self.name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the context manager, stopping the timer and logging metrics."""
        self.end_time = time.time()
        duration = self.end_time - self.start_time
        self.stats["duration"] = duration
        self.logger.info(f"Completed {self.name} in {duration:.2f} seconds")

        if self.stats:
            self.logger.info(f"Metrics for {self.name}: {self.stats}")

    def record(self, metric: str, value: Any) -> None:
        """Record a metric.

        Args:
            metric: The name of the metric.
            value: The value of the metric.
        """
        self.stats[metric] = value
        self.logger.debug(f"Recorded metric {metric}={value} for {self.name}")
