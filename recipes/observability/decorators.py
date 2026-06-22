"""Decorator recipes for automatic method logging and progress tracking."""

import time
from typing import Any

from glean.indexing.observability import (
    ConnectorObservability,
    track_crawl_progress,
    with_observability,
)


@with_observability()
class BasicConnector:
    """Connector with automatic logging for all public methods."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def fetch_users(self) -> list[dict[str, Any]]:
        time.sleep(0.1)
        return [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}]

    def fetch_documents(self) -> list[dict[str, Any]]:
        time.sleep(0.1)
        return [{"id": "doc1", "title": "Document 1"}]


@with_observability(exclude_methods=["_internal_helper"])
class ConnectorWithExclusions:
    """Connector that excludes specific methods from logging."""

    def fetch_data(self) -> list[dict[str, Any]]:
        return self._internal_helper()

    def _internal_helper(self) -> list[dict[str, Any]]:
        return [{"id": "1"}]


@with_observability(include_args=True, include_return=True)
class VerboseConnector:
    """Connector with verbose logging including arguments and return values."""

    def fetch_page(self, page: int, per_page: int = 10) -> dict[str, Any]:
        return {"page": page, "items": [{"id": str(i)} for i in range(per_page)]}


@with_observability()
class ConnectorWithObservability:
    """Connector that uses both decorator and ConnectorObservability instance."""

    def __init__(self, connector_name: str) -> None:
        self._observability = ConnectorObservability(connector_name)

    def fetch_data(self) -> list[dict[str, Any]]:
        time.sleep(0.1)
        return [{"id": "1"}]


class ProgressTrackingConnector:
    """Connector using track_crawl_progress decorator."""

    def __init__(self) -> None:
        self._observability = ConnectorObservability("progress_connector")

    @track_crawl_progress
    def fetch_users(self) -> list[dict[str, Any]]:
        return [{"id": str(i), "name": f"User {i}"} for i in range(100)]

    @track_crawl_progress
    def fetch_documents(self) -> list[dict[str, Any]]:
        return [{"id": str(i), "title": f"Doc {i}"} for i in range(50)]


@with_observability(include_args=True)
class ErrorHandlingConnector:
    """Connector demonstrating automatic error logging."""

    def __init__(self) -> None:
        self._observability = ConnectorObservability("error_connector")

    def fetch_data(self, endpoint: str) -> list[dict[str, Any]]:
        if endpoint == "/error":
            raise ValueError("Invalid endpoint")
        return [{"id": "1"}]


def use_basic_decorator() -> None:
    """Use with_observability decorator with default settings."""
    connector = BasicConnector(api_key="test-key")
    users = connector.fetch_users()
    docs = connector.fetch_documents()
    print(f"Fetched {len(users)} users and {len(docs)} documents")


def use_verbose_decorator() -> None:
    """Use with_observability decorator with argument and return logging."""
    connector = VerboseConnector()
    result = connector.fetch_page(page=1, per_page=5)
    print(f"Fetched page: {result}")


def use_progress_tracking() -> None:
    """Use track_crawl_progress decorator to track item counts."""
    connector = ProgressTrackingConnector()
    users = connector.fetch_users()
    docs = connector.fetch_documents()

    metrics = connector._observability.get_metrics_summary()
    print(f"Total items crawled: {metrics.get('total_items_crawled', 0)}")


def use_error_handling() -> None:
    """Demonstrate automatic error logging with decorators."""
    connector = ErrorHandlingConnector()

    try:
        connector.fetch_data("/error")
    except ValueError:
        print("Error was automatically logged")


if __name__ == "__main__":
    from glean.indexing.observability import setup_connector_logging

    setup_connector_logging("decorator_examples", use_structured_logging=True)

    use_basic_decorator()
    use_verbose_decorator()
    use_progress_tracking()
    use_error_handling()
