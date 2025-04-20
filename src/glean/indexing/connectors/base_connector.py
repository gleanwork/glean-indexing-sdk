"""Base connector class for the Glean Connector SDK."""

import logging
from abc import ABC, abstractmethod
from typing import Generic

from glean.indexing.models import IndexingMode, TGleanModel, TSourceData

logger = logging.getLogger(__name__)


class BaseConnector(ABC, Generic[TSourceData, TGleanModel]):
    """
    Base class for all Glean connectors.

    Type Parameters:
        TSourceData: The type of data from external sources
        TGleanModel: The type of Glean API model objects to be indexed
    """

    def __init__(self, name: str):
        """Initialize the connector.

        Args:
            name: The name of the connector.
        """
        self.name = name

    @abstractmethod
    def index_data(self, mode: IndexingMode = IndexingMode.FULL) -> None:
        """Index data from the connector to Glean."""
        pass
