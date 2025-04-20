"""Base streaming data client interface for Glean connectors."""

from abc import ABC, abstractmethod
from typing import Any, Generator, Generic

from glean.indexing.models import TSourceData


class BaseStreamingDataClient(ABC, Generic[TSourceData]):
    """
    Base class for streaming data clients that fetch data in chunks.

    Use this for large datasets to minimize memory usage.
    This class provides an iterable interface for data retrieval, allowing
    for efficient processing of large datasets without loading all data into memory at once.

    Type Parameters:
        TSourceData: The type of data yielded from the external source
    """

    @abstractmethod
    def get_source_data(self, **kwargs: Any) -> Generator[TSourceData, None, None]:
        """
        Retrieves source data as a generator.

        This method should be implemented to return a generator
        that yields data items one at a time or in small batches.

        Args:
            **kwargs: Additional keyword arguments for customizing data retrieval.

        Returns:
            A generator of data items.
        """
        pass


# Alias for backward compatibility during transition
StreamingConnectorDataClient = BaseStreamingDataClient
