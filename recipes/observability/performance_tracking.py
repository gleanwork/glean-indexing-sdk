"""Performance tracking recipes using context managers and callbacks."""

import time
from typing import Any

from glean.indexing.observability import (
    ConnectorObservability,
    PerformanceTracker,
    ProgressCallback,
)


def track_operation_performance() -> None:
    """Track performance of a single operation using PerformanceTracker."""
    with PerformanceTracker("data_fetch"):
        time.sleep(0.5)
        fetch_data_from_api()


def track_with_observability_integration() -> None:
    """Track performance with ConnectorObservability integration."""
    obs = ConnectorObservability("my_connector")

    with PerformanceTracker("transform_items", observability=obs):
        time.sleep(0.3)
        transform_items()

    metrics = obs.get_metrics_summary()
    print(f"Transform duration: {metrics.get('transform_items_duration', 0):.3f}s")


def track_with_error_handling() -> None:
    """Track performance even when operations fail."""
    obs = ConnectorObservability("my_connector")

    try:
        with PerformanceTracker("api_call", observability=obs):
            time.sleep(0.1)
            raise ValueError("API error")
    except ValueError:
        pass

    metrics = obs.get_metrics_summary()
    print(f"API call errors: {metrics.get('api_call_errors', 0)}")


def track_progress_with_known_total() -> None:
    """Track progress when total item count is known."""
    total_items = 1000
    progress = ProgressCallback(total_items=total_items)

    for i in range(0, total_items, 100):
        time.sleep(0.1)
        process_batch(i, min(i + 100, total_items))
        progress.update(items_processed=100)

    progress.complete()


def track_progress_without_total() -> None:
    """Track progress when total item count is unknown."""
    progress = ProgressCallback()

    for batch_num in range(10):
        time.sleep(0.1)
        items = fetch_next_batch(batch_num)
        progress.update(items_processed=len(items))

    progress.complete()


def track_nested_operations() -> None:
    """Track performance of nested operations."""
    obs = ConnectorObservability("my_connector")

    with PerformanceTracker("full_sync", observability=obs):
        with PerformanceTracker("fetch_phase", observability=obs):
            time.sleep(0.2)
            fetch_data_from_api()

        with PerformanceTracker("transform_phase", observability=obs):
            time.sleep(0.3)
            transform_items()

        with PerformanceTracker("upload_phase", observability=obs):
            time.sleep(0.1)
            upload_to_glean()

    metrics = obs.get_metrics_summary()
    for key, value in metrics.items():
        if key.endswith("_duration"):
            print(f"{key}: {value:.3f}s")


def track_multiple_operations() -> None:
    """Track multiple operations with separate trackers."""
    obs = ConnectorObservability("my_connector")

    operations = ["fetch_users", "fetch_groups", "fetch_permissions"]

    for operation in operations:
        with PerformanceTracker(operation, observability=obs):
            time.sleep(0.15)

    metrics = obs.get_metrics_summary()
    print(f"Tracked {len([k for k in metrics if k.endswith('_duration')])} operations")


def fetch_data_from_api() -> list[dict[str, Any]]:
    """Simulate API data fetch."""
    return [{"id": str(i)} for i in range(100)]


def transform_items() -> None:
    """Simulate data transformation."""
    pass


def upload_to_glean() -> None:
    """Simulate upload to Glean."""
    pass


def process_batch(start: int, end: int) -> None:
    """Process a batch of items."""
    pass


def fetch_next_batch(batch_num: int) -> list[dict[str, Any]]:
    """Fetch next batch from API."""
    return [{"id": str(i)} for i in range(batch_num * 50, (batch_num + 1) * 50)]


if __name__ == "__main__":
    from glean.indexing.observability import setup_connector_logging

    setup_connector_logging("performance_examples")

    track_operation_performance()
    track_with_observability_integration()
    track_progress_with_known_total()
    track_nested_operations()
