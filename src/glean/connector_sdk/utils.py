"""Utility classes for Glean connectors."""

import logging
import time
from typing import Any, Dict, Generator, Iterator, List, Optional, Sequence, TypeVar

from jinja2 import Environment, Template


logger = logging.getLogger(__name__)

T = TypeVar("T")


class ContentFormatter:
    """A utility for formatting content using Jinja2 templates."""
    
    def __init__(self, template_str: str):
        """Initialize the ContentFormatter.
        
        Args:
            template_str: A Jinja2 template string.
        """
        self.env = Environment(autoescape=True)
        self.template = self.env.from_string(template_str)
    
    def render(self, context: Dict[str, Any]) -> str:
        """Render the template with the given context.
        
        Args:
            context: A dictionary containing the context for rendering.
            
        Returns:
            The rendered template as a string.
        """
        return self.template.render(**context)
    
    @classmethod
    def from_file(cls, template_path: str) -> "ContentFormatter":
        """Create a ContentFormatter from a template file.
        
        Args:
            template_path: Path to a Jinja2 template file.
            
        Returns:
            A ContentFormatter instance.
        """
        with open(template_path, "r", encoding="utf-8") as f:
            template_str = f.read()
        return cls(template_str)


class BatchProcessor:
    """A utility for processing data in batches."""
    
    def __init__(self, data: Sequence[T], batch_size: int = 100):
        """Initialize the BatchProcessor.
        
        Args:
            data: The data to process in batches.
            batch_size: The size of each batch.
        """
        self.data = data
        self.batch_size = batch_size
    
    def __iter__(self) -> Iterator[List[T]]:
        """Iterate over the data in batches.
        
        Yields:
            Lists of items of size batch_size (except possibly the last batch).
        """
        for i in range(0, len(self.data), self.batch_size):
            yield self.data[i:i + self.batch_size]


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