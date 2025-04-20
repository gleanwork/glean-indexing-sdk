"""Observability infrastructure for Glean connectors."""

import functools
import logging
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, TypeVar

logger = logging.getLogger(__name__)

# Type variable for decorated classes
T = TypeVar("T")


class ConnectorObservability:
    """
    Centralized observability for connector operations.

    Tracks metrics, performance, and provides structured logging.
    """

    def __init__(self, connector_name: str):
        self.connector_name = connector_name
        self.metrics: Dict[str, Any] = defaultdict(int)
        self.timers: Dict[str, float] = {}
        self.start_time: Optional[float] = None

    def start_execution(self):
        """Mark the start of connector execution."""
        self.start_time = time.time()
        logger.info(f"[{self.connector_name}] Execution started")

    def end_execution(self):
        """Mark the end of connector execution."""
        if self.start_time:
            duration = time.time() - self.start_time
            self.metrics["total_execution_time"] = duration
            logger.info(f"[{self.connector_name}] Execution completed in {duration:.2f}s")

    def record_metric(self, key: str, value: Any):
        """Record a custom metric."""
        self.metrics[key] = value
        logger.debug(f"[{self.connector_name}] Metric recorded: {key}={value}")

    def increment_counter(self, key: str, value: int = 1):
        """Increment a counter metric."""
        self.metrics[key] += value

    def start_timer(self, operation: str):
        """Start timing an operation."""
        self.timers[operation] = time.time()

    def end_timer(self, operation: str):
        """End timing an operation and record the duration."""
        if operation in self.timers:
            duration = time.time() - self.timers[operation]
            self.record_metric(f"{operation}_duration", duration)
            del self.timers[operation]
            return duration
        return None

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get a summary of all collected metrics."""
        return dict(self.metrics)


def with_observability(
    exclude_methods: Optional[List[str]] = None,
    include_args: bool = False,
    include_return: bool = False,
) -> Callable[[type], type]:
    """
    Class decorator that adds comprehensive logging to all public methods.

    Args:
        exclude_methods: List of method names to exclude from logging
        include_args: Whether to log method arguments
        include_return: Whether to log return values

    Returns:
        Decorated class with enhanced logging
    """
    if exclude_methods is None:
        exclude_methods = ["__init__", "__str__", "__repr__"]

    def decorator(cls: type) -> type:
        def wrap_method(method: Callable[..., Any]) -> Callable[..., Any]:
            if method.__name__ in exclude_methods:
                return method

            @functools.wraps(method)
            def wrapped_method(self, *args: Any, **kwargs: Any) -> Any:
                method_name = method.__name__
                class_name = self.__class__.__name__

                # Log method start
                if include_args:
                    logger.info(
                        f"[{class_name}] {method_name} started with args={args}, kwargs={kwargs}"
                    )
                else:
                    logger.info(f"[{class_name}] {method_name} started")

                start_time = time.time()

                try:
                    result = method(self, *args, **kwargs)
                    duration = time.time() - start_time

                    # Log successful completion
                    if include_return:
                        logger.info(
                            f"[{class_name}] {method_name} completed in {duration:.3f}s with result={result}"
                        )
                    else:
                        logger.info(f"[{class_name}] {method_name} completed in {duration:.3f}s")

                    # Record timing metric if observability is available
                    if hasattr(self, "_observability"):
                        self._observability.record_metric(f"{method_name}_duration", duration)

                    return result

                except Exception as e:
                    duration = time.time() - start_time
                    logger.error(f"[{class_name}] {method_name} failed after {duration:.3f}s: {e}")

                    # Record error metric if observability is available
                    if hasattr(self, "_observability"):
                        self._observability.increment_counter(f"{method_name}_errors")

                    raise

            return wrapped_method

        # Apply the wrapper to all public methods
        for attr_name, attr_value in cls.__dict__.items():
            if callable(attr_value) and not attr_name.startswith("_"):
                setattr(cls, attr_name, wrap_method(attr_value))

        return cls

    return decorator


def track_crawl_progress(method: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator that tracks crawling progress and item counts.

    Expects the method to return a sequence and increments crawl metrics.
    """

    @functools.wraps(method)
    def wrapper(self, *args: Any, **kwargs: Any) -> Any:
        result = method(self, *args, **kwargs)

        # Track item count if result is a sequence
        if hasattr(result, "__len__"):
            item_count = len(result)
            if hasattr(self, "_observability"):
                self._observability.increment_counter("items_processed", item_count)
                self._observability.increment_counter("total_items_crawled", item_count)
            logger.info(f"Processed {item_count} items in {method.__name__}")

        return result

    return wrapper


class PerformanceTracker:
    """
    Context manager for tracking performance of operations.
    """

    def __init__(self, operation_name: str, observability: Optional[ConnectorObservability] = None):
        self.operation_name = operation_name
        self.observability = observability
        self.start_time: Optional[float] = None

    def __enter__(self):
        self.start_time = time.time()
        logger.info(f"Starting operation: {self.operation_name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = time.time() - self.start_time

            if exc_type is None:
                logger.info(f"Operation '{self.operation_name}' completed in {duration:.3f}s")
            else:
                logger.error(
                    f"Operation '{self.operation_name}' failed after {duration:.3f}s: {exc_val}"
                )

            if self.observability:
                self.observability.record_metric(f"{self.operation_name}_duration", duration)
                if exc_type is not None:
                    self.observability.increment_counter(f"{self.operation_name}_errors")


class ProgressCallback:
    """
    Callback interface for tracking connector progress.
    """

    def __init__(self, total_items: Optional[int] = None):
        self.total_items = total_items
        self.processed_items = 0
        self.start_time = time.time()

    def update(self, items_processed: int):
        """Update progress with number of items processed."""
        self.processed_items += items_processed
        elapsed = time.time() - self.start_time

        if self.total_items:
            progress_pct = (self.processed_items / self.total_items) * 100
            logger.info(
                f"Progress: {self.processed_items}/{self.total_items} ({progress_pct:.1f}%) - "
                f"Rate: {self.processed_items / elapsed:.1f} items/sec"
            )
        else:
            logger.info(
                f"Progress: {self.processed_items} items processed - "
                f"Rate: {self.processed_items / elapsed:.1f} items/sec"
            )

    def complete(self):
        """Mark progress as complete."""
        elapsed = time.time() - self.start_time
        logger.info(
            f"Processing complete: {self.processed_items} items in {elapsed:.2f}s "
            f"(avg rate: {self.processed_items / elapsed:.1f} items/sec)"
        )


def setup_connector_logging(
    connector_name: str, log_level: str = "INFO", log_format: Optional[str] = None
):
    """
    Set up standardized logging for a connector.

    Args:
        connector_name: Name of the connector for log identification
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_format: Custom log format string
    """
    if log_format is None:
        log_format = f"%(asctime)s - {connector_name} - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format,
        handlers=[
            logging.StreamHandler(),
            # Add file handler if needed
            # logging.FileHandler(f"{connector_name}.log")
        ],
    )

    logger.info(f"Logging configured for connector: {connector_name}")
