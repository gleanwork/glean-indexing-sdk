"""Base datasource connector for the Glean Connector SDK."""

import logging
from abc import abstractmethod
from typing import List, Optional, Sequence

from glean.connector_sdk.connector.base_connector import BaseConnector
from glean.connector_sdk.models import DocumentDefinition, IndexingMode


logger = logging.getLogger(__name__)


class BaseDatasourceConnector(BaseConnector):
    """Base class for datasource connectors."""

    def index_data(self, mode: IndexingMode = IndexingMode.FULL) -> None:
        """Index data from the datasource to Glean.

        Args:
            mode: The indexing mode to use (FULL or INCREMENTAL).
        """
        logger.info(
            f"Starting {mode.name.lower()} indexing for datasource '{self.name}'"
        )

        since = None
        if mode == IndexingMode.INCREMENTAL:
            # In a real implementation, this would get the last indexing timestamp
            since = "2023-01-01T00:00:00Z"

        # Get data from source
        data = self.get_data(since=since)
        logger.info(f"Retrieved {len(data)} items from datasource")

        # Transform to Glean document format
        documents = self.transform(data)
        logger.info(f"Transformed {len(documents)} documents")

        # Post to Glean index
        self.post_to_index(documents)
        logger.info(f"Indexed {len(documents)} documents to Glean")

    @abstractmethod
    def get_data(self, since: Optional[str] = None) -> Sequence[dict]:
        """Get data from the datasource.

        Args:
            since: If provided, only get data modified since this timestamp.

        Returns:
            A sequence of dictionaries containing the source data.
        """
        pass

    @abstractmethod
    def transform(self, data: Sequence[dict]) -> List[DocumentDefinition]:
        """Transform source data to Glean document format.

        Args:
            data: The source data to transform.

        Returns:
            A list of DocumentDefinition objects ready for indexing.
        """
        pass

    def post_to_index(self, docs: List[DocumentDefinition]) -> None:
        """Post documents to the Glean index.

        Args:
            docs: The documents to index.
        """
        # In a real implementation, this would use the Glean API client
        client = self.get_client()
        client.batch_index_documents(datasource=self.name, documents=docs) 