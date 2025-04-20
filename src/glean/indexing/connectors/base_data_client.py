"""Base data client interface for standard Glean connectors."""

from abc import ABC, abstractmethod
from typing import Any, Generic, Sequence

from glean.indexing.models import TSourceData


class BaseDataClient(ABC, Generic[TSourceData]):
    """
    Base class for all connector data clients.

    This interface defines how connectors fetch data from external sources.
    All data clients should inherit from this class and implement get_source_data.

    Type Parameters:
        TSourceData: The type of data returned from the external source
    """

    @abstractmethod
    def get_source_data(self, **kwargs: Any) -> Sequence[TSourceData]:
        """
        Fetch all data from the external source.

        Args:
            **kwargs: Additional parameters for data fetching (e.g., since timestamp)

        Returns:
            A sequence of data items from the source
        """
        pass


# Alias for backward compatibility during transition
BaseConnectorDataClient = BaseDataClient
