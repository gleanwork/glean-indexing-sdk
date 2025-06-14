"""Base connector class for the Glean Connector SDK."""

import logging
from abc import ABC, abstractmethod
from typing import Generic, Optional, Sequence

from glean.indexing.models import IndexingMode, TGleanModel, TSourceData

logger = logging.getLogger(__name__)


class BaseConnector(ABC, Generic[TSourceData, TGleanModel]):
    """
    Abstract base class for all Glean connectors.

    This class defines the core interface and lifecycle for all connector types (datasource, people, streaming, etc.).
    Connector implementors should inherit from this class and provide concrete implementations for all abstract methods.

    Type Parameters:
        TSourceData: The type of raw data fetched from the external source (e.g., dict, TypedDict, or custom model).
        TGleanModel: The type of Glean API model object produced by the connector (e.g., DocumentDefinition, EmployeeInfoDefinition).

    Required Methods for Subclasses:
        - get_data(since: Optional[str] = None) -> Sequence[TSourceData]:
            Fetches source data from the external system. Should support incremental fetches if possible.
        - transform(data: Sequence[TSourceData]) -> List[TGleanModel]:
            Transforms source data into Glean API model objects ready for indexing.
        - index_data(mode: IndexingMode = IndexingMode.FULL) -> None:
            Orchestrates the full indexing process (fetch, transform, upload).

    Attributes:
        name (str): The unique name of the connector (should be snake_case).

    Example:
        class MyConnector(BaseConnector[MyRawType, DocumentDefinition]):
            ...
    """

    def __init__(self, name: str):
        """Initialize the connector.

        Args:
            name: The name of the connector.
        """
        self.name = name

    @abstractmethod
    def get_data(self, since: Optional[str] = None) -> Sequence[TSourceData]:
        """Get data from the data client or source system."""
        pass

    @abstractmethod
    def transform(self, data: Sequence[TSourceData]) -> Sequence[TGleanModel]:
        """Transform source data to Glean model objects."""
        pass

    @abstractmethod
    def index_data(self, mode: IndexingMode = IndexingMode.FULL) -> None:
        """Index data from the connector to Glean."""
        pass
