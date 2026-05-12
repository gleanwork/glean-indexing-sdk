"""Ready-made data clients for tests.

Most connector tests want to feed a fixed list of source records through a
connector and assert on the resulting document/employee output. Without
these helpers, every test has to subclass `BaseDataClient` (or its streaming
siblings) just to return a list. These three classes provide that one-liner.
"""

from typing import Any, AsyncGenerator, Generator, Generic, Sequence

from glean.indexing.connectors.base_async_streaming_data_client import BaseAsyncStreamingDataClient
from glean.indexing.connectors.base_data_client import BaseDataClient
from glean.indexing.connectors.base_streaming_data_client import BaseStreamingDataClient
from glean.indexing.models import TSourceData


class StaticDataClient(BaseDataClient[TSourceData], Generic[TSourceData]):
    """`BaseDataClient` that returns a fixed list of items each call.

    Each `get_source_data` call returns a fresh `list(items)` so callers can
    mutate the result without affecting subsequent calls.
    """

    def __init__(self, items: Sequence[TSourceData]) -> None:
        """Initialize with a fixed sequence of source records.

        Args:
            items: Records the connector will receive when it calls `get_source_data`.
        """
        self._items: Sequence[TSourceData] = items

    def get_source_data(self, **kwargs: Any) -> Sequence[TSourceData]:
        """Return a fresh list of the configured items."""
        return list(self._items)


class StaticStreamingDataClient(BaseStreamingDataClient[TSourceData], Generic[TSourceData]):
    """`BaseStreamingDataClient` that yields a fixed list of items each call.

    Each call to `get_source_data` returns a fresh generator so iteration
    state does not leak between calls.
    """

    def __init__(self, items: Sequence[TSourceData]) -> None:
        """Initialize with a fixed sequence of source records.

        Args:
            items: Records the connector will receive when it iterates `get_source_data`.
        """
        self._items: Sequence[TSourceData] = items

    def get_source_data(self, **kwargs: Any) -> Generator[TSourceData, None, None]:
        """Yield each configured item in order."""
        for item in self._items:
            yield item


class StaticAsyncStreamingDataClient(
    BaseAsyncStreamingDataClient[TSourceData], Generic[TSourceData]
):
    """`BaseAsyncStreamingDataClient` that async-yields a fixed list of items.

    Each call to `get_source_data` returns a fresh async generator.
    """

    def __init__(self, items: Sequence[TSourceData]) -> None:
        """Initialize with a fixed sequence of source records.

        Args:
            items: Records the connector will receive when it iterates `get_source_data`.
        """
        self._items: Sequence[TSourceData] = items

    async def get_source_data(self, **kwargs: Any) -> AsyncGenerator[TSourceData, None]:
        """Async-yield each configured item in order."""
        for item in self._items:
            yield item
