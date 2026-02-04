"""Base async streaming data client for fetching data in chunks."""

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Generic

from glean.indexing.models import TSourceData


class BaseAsyncStreamingDataClient(ABC, Generic[TSourceData]):
    """
    Base class for async streaming data clients that fetch data in chunks.

    Use this for large datasets with async APIs to minimize memory usage
    and maximize I/O throughput.

    Type Parameters:
        TSourceData: The type of data yielded from the external source

    Example:
        class MyAsyncDataClient(BaseAsyncStreamingDataClient[MyDocData]):
            async def get_source_data(self, **kwargs) -> AsyncGenerator[MyDocData, None]:
                async for page in self.fetch_pages():
                    for item in page:
                        yield item
    """

    @abstractmethod
    async def get_source_data(self, **kwargs: Any) -> AsyncGenerator[TSourceData, None]:
        """
        Retrieves source data as an async generator.

        This method should be implemented to return an async generator
        that yields data items one at a time or in small batches.

        Args:
            **kwargs: Additional keyword arguments for customizing data retrieval.

        Yields:
            Individual data items from the external source.
        """
        if False:
            yield  # type: ignore[misc]


AsyncStreamingDataClient = BaseAsyncStreamingDataClient
