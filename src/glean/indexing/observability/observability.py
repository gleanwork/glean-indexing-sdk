"""Observability infrastructure for Glean connectors."""

import functools
import logging
import time
import uuid
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, TypeVar

from .formatters import StructuredFormatter
from .providers import InMemoryMetricsProvider, MetricsProvider, MetricType

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ConnectorObservability:
    """
    Centralized observability for connector operations.

    Tracks metrics, performance, and provides structured logging.
    """

    def __init__(
        self,
        connector_name: str,
        datasource: Optional[str] = None,
        crawl_mode: Optional[str] = None,
        run_id: Optional[str] = None,
        metrics_provider: Optional[MetricsProvider] = None,
    ):
        self.connector_name = connector_name
        self.datasource = datasource or connector_name
        self.crawl_mode = crawl_mode
        self.run_id = run_id or str(uuid.uuid4())
        self.metrics_provider = metrics_provider or InMemoryMetricsProvider()
        self.metrics: Dict[str, Any] = defaultdict(int)
        self.timers: Dict[str, float] = {}
        self.start_time: Optional[float] = None
        self._execution_failed: bool = False

    def get_common_fields(self, operation: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        """Get common fields for structured logging."""
        fields = {
            "connector": self.connector_name,
            "datasource": self.datasource,
            "run_id": self.run_id,
        }
        if self.crawl_mode:
            fields["crawl_mode"] = self.crawl_mode
        if operation:
            fields["operation"] = operation
        fields.update(kwargs)
        return fields

    def _get_metric_labels(self, **kwargs: str) -> Dict[str, str]:
        """Get base metric labels with optional additional labels."""
        labels = {
            "connector": self.connector_name,
            "datasource": self.datasource,
        }
        if self.crawl_mode:
            labels["crawl_mode"] = self.crawl_mode
        labels.update(kwargs)
        return labels

    def start_execution(self) -> None:
        """Mark the start of connector execution."""
        self.start_time = time.time()
        self._execution_failed = False
        logger.info(
            "Crawl started",
            extra=self.get_common_fields(
                operation="crawl_started",
                start_time=self.start_time,
            ),
        )

    def end_execution(self) -> None:
        """Mark the end of connector execution."""
        if self.start_time and not self._execution_failed:
            duration = time.time() - self.start_time
            duration_ms = int(duration * 1000)
            self.metrics["total_execution_time"] = duration
            self.metrics_provider.emit_metric(
                "connector_execution_duration_ms",
                float(duration_ms),
                MetricType.HISTOGRAM,
                self._get_metric_labels(),
            )
            logger.info(
                "Crawl completed successfully",
                extra=self.get_common_fields(
                    operation="crawl_completed",
                    duration_ms=duration_ms,
                    status="success",
                ),
            )
        self.metrics_provider.flush()

    def fail_execution(self, error: Exception) -> None:
        """Mark the execution as failed."""
        import sys

        self._execution_failed = True
        duration_ms = None
        if self.start_time:
            duration = time.time() - self.start_time
            duration_ms = int(duration * 1000)
            self.metrics_provider.emit_metric(
                "connector_execution_duration_ms",
                float(duration_ms),
                MetricType.HISTOGRAM,
                self._get_metric_labels(),
            )

        exc_info = sys.exc_info()
        if exc_info[1] is not error:
            exc_info = (type(error), error, None)

        logger.error(
            f"Crawl failed: {error}",
            extra=self.get_common_fields(
                operation="crawl_failed",
                status="failed",
                error_type=type(error).__name__,
                error_message=str(error),
                duration_ms=duration_ms,
            ),
            exc_info=exc_info,
        )
        self.metrics_provider.flush()

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

    def log_data_fetch_started(self, **kwargs: Any) -> None:
        """Log the start of data fetching phase."""
        logger.info(
            "Data fetch started",
            extra=self.get_common_fields(operation="data_fetch_started", **kwargs),
        )

    def log_data_fetch_completed(self, item_count: int, duration_ms: int, **kwargs: Any) -> None:
        """Log successful completion of data fetching."""
        logger.info(
            f"Data fetch completed: {item_count} items",
            extra=self.get_common_fields(
                operation="data_fetch_completed",
                item_count=item_count,
                duration_ms=duration_ms,
                status="success",
                **kwargs,
            ),
        )

    def log_transform_started(self, item_count: int, **kwargs: Any) -> None:
        """
        Log the start of data transformation.

        Args:
            item_count: Number of items to transform
            **kwargs: Additional fields to include
        """
        logger.info(
            f"Transform started: {item_count} items",
            extra=self.get_common_fields(
                operation="transform_started",
                item_count=item_count,
                **kwargs,
            ),
        )

    def log_transform_completed(self, input_count: int, output_count: int, duration_ms: int, **kwargs: Any) -> None:
        """
        Log successful completion of data transformation.

        Args:
            input_count: Number of input items
            output_count: Number of output items
            duration_ms: Duration in milliseconds
            **kwargs: Additional fields to include
        """
        logger.info(
            f"Transform completed: {input_count} → {output_count} items",
            extra=self.get_common_fields(
                operation="transform_completed",
                input_count=input_count,
                output_count=output_count,
                duration_ms=duration_ms,
                status="success",
                **kwargs,
            ),
        )

    def log_batch_upload_started(
        self,
        batch_index: int,
        batch_count: int,
        batch_size: int,
        entity_type: str = "document",
        **kwargs: Any,
    ) -> None:
        """
        Log the start of a batch upload.

        Args:
            batch_index: Current batch number (0-indexed)
            batch_count: Total number of batches
            batch_size: Number of items in this batch
            entity_type: Type of entity being uploaded (document, user, group, etc.)
            **kwargs: Additional fields to include
        """
        logger.info(
            f"Batch upload started: {batch_index + 1}/{batch_count} ({batch_size} {entity_type}s)",
            extra=self.get_common_fields(
                operation="batch_upload_started",
                batch_index=batch_index,
                batch_count=batch_count,
                batch_size=batch_size,
                entity_type=entity_type,
                **kwargs,
            ),
        )

    def log_batch_upload_completed(
        self,
        batch_index: int,
        batch_count: int,
        batch_size: int,
        duration_ms: int,
        entity_type: str = "document",
        **kwargs: Any,
    ) -> None:
        """
        Log successful completion of a batch upload.

        Args:
            batch_index: Current batch number (0-indexed)
            batch_count: Total number of batches
            batch_size: Number of items uploaded
            duration_ms: Duration in milliseconds
            entity_type: Type of entity uploaded
            **kwargs: Additional fields to include
        """
        logger.info(
            f"Batch upload completed: {batch_index + 1}/{batch_count} ({batch_size} {entity_type}s)",
            extra=self.get_common_fields(
                operation="batch_upload_completed",
                batch_index=batch_index,
                batch_count=batch_count,
                batch_size=batch_size,
                duration_ms=duration_ms,
                entity_type=entity_type,
                status="success",
                **kwargs,
            ),
        )

    def log_batch_upload_failed(
        self,
        batch_index: int,
        batch_count: int,
        error: Exception,
        entity_type: str = "document",
        **kwargs: Any,
    ) -> None:
        """
        Log a failed batch upload.

        Args:
            batch_index: Current batch number (0-indexed)
            batch_count: Total number of batches
            error: The exception that caused the failure
            entity_type: Type of entity being uploaded
            **kwargs: Additional fields to include
        """
        import sys

        exc_info = sys.exc_info()
        if exc_info[1] is not error:
            exc_info = (type(error), error, None)

        logger.error(
            f"Batch upload failed: {batch_index + 1}/{batch_count} - {error}",
            extra=self.get_common_fields(
                operation="batch_upload_failed",
                batch_index=batch_index,
                batch_count=batch_count,
                entity_type=entity_type,
                status="failed",
                error_type=type(error).__name__,
                error_message=str(error),
                **kwargs,
            ),
            exc_info=exc_info,
        )

    def record_upload_batch_size(self, batch_size: int) -> None:
        """Record the size of an upload batch."""
        self.metrics_provider.emit_metric(
            "upload_batch_size",
            float(batch_size),
            MetricType.HISTOGRAM,
            self._get_metric_labels(),
        )

    def record_upload_throughput(self, docs_per_sec: float) -> None:
        """Record upload throughput in documents per second."""
        self.metrics_provider.emit_metric(
            "upload_throughput",
            docs_per_sec,
            MetricType.GAUGE,
            self._get_metric_labels(),
        )

    def record_api_request_latency(self, latency_ms: float, endpoint: str) -> None:
        """Record API request latency in milliseconds."""
        self.metrics_provider.emit_metric(
            "api_request_latency_ms",
            latency_ms,
            MetricType.HISTOGRAM,
            self._get_metric_labels(endpoint=endpoint),
        )

    def record_api_request_count(self, endpoint: str) -> None:
        """Record an API request count."""
        self.metrics_provider.emit_metric(
            "api_request_count",
            1.0,
            MetricType.COUNTER,
            self._get_metric_labels(endpoint=endpoint),
        )

    def record_api_request_error(self, endpoint: str, error_type: str) -> None:
        """Record an API request error."""
        self.metrics_provider.emit_metric(
            "api_request_errors",
            1.0,
            MetricType.COUNTER,
            self._get_metric_labels(endpoint=endpoint, error_type=error_type),
        )

    def record_retry(self, operation: str) -> None:
        """Record a retry attempt."""
        self.metrics_provider.emit_metric(
            "retry_count",
            1.0,
            MetricType.COUNTER,
            self._get_metric_labels(operation=operation),
        )

    def record_crawl_success(self) -> None:
        """Record a successful crawl completion."""
        self.metrics_provider.emit_metric(
            "crawl_success",
            1.0,
            MetricType.COUNTER,
            self._get_metric_labels(),
        )

    def record_crawl_failure(self, error_type: str) -> None:
        """Record a failed crawl."""
        self.metrics_provider.emit_metric(
            "crawl_failure",
            1.0,
            MetricType.COUNTER,
            self._get_metric_labels(error_type=error_type),
        )


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

                    if include_return:
                        logger.info(
                            f"[{class_name}] {method_name} completed in {duration:.3f}s with result={result}"
                        )
                    else:
                        logger.info(f"[{class_name}] {method_name} completed in {duration:.3f}s")

                    if hasattr(self, "_observability"):
                        self._observability.record_metric(f"{method_name}_duration", duration)

                    return result

                except Exception as e:
                    duration = time.time() - start_time
                    logger.error(f"[{class_name}] {method_name} failed after {duration:.3f}s: {e}")

                    if hasattr(self, "_observability"):
                        self._observability.increment_counter(f"{method_name}_errors")

                    raise

            return wrapped_method

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
    connector_name: str,
    log_level: str = "INFO",
    log_format: Optional[str] = None,
    *,
    use_structured_logging: bool = False,
    formatter: Optional[logging.Formatter] = None,
    extra_handlers: Optional[List[logging.Handler]] = None,
) -> None:
    """
    Set up standardized logging for a connector.

    Args:
        connector_name: Name of the connector for log identification
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_format: Custom log format string (ignored if formatter is provided)
        use_structured_logging: Enable structured JSON logging
        formatter: Custom formatter instance (overrides use_structured_logging and log_format)
        extra_handlers: Additional handlers to add beyond the default StreamHandler
    """
    logging.root.handlers = []
    logging.root.setLevel(getattr(logging, log_level.upper()))

    if formatter is None:
        if use_structured_logging:
            formatter = StructuredFormatter()
        else:
            if log_format is None:
                log_format = f"%(asctime)s - {connector_name} - %(name)s - %(levelname)s - %(message)s"
            formatter = logging.Formatter(log_format)

    handlers = [logging.StreamHandler()]
    if extra_handlers:
        handlers.extend(extra_handlers)

    for handler in handlers:
        handler.setFormatter(formatter)
        logging.root.addHandler(handler)

    if isinstance(formatter, StructuredFormatter):
        logger.info(
            "Structured logging configured",
            extra={"connector": connector_name, "log_level": log_level},
        )
    else:
        logger.info(f"Logging configured for connector: {connector_name}")
