"""Example datasource connector implementation."""

import logging
from typing import List, Optional, Sequence

from glean.connector_sdk.connector.base_datasource_connector import BaseDatasourceConnector
from glean.connector_sdk.examples.mock_clients import MockDataSourceClient
from glean.connector_sdk.models import DocumentDefinition
from glean.connector_sdk.utils import BatchProcessor


logger = logging.getLogger(__name__)


class MyDatasourceConnector(BaseDatasourceConnector):
    """Example datasource connector implementation."""

    name = "my_datasource"

    def get_data(self, since: Optional[str] = None) -> Sequence[dict]:
        """Get data from the datasource.

        Args:
            since: If provided, only get data modified since this timestamp.

        Returns:
            A sequence of dictionaries containing the source data.
        """
        logger.info(f"Fetching data from source{' since ' + since if since else ''}")

        # Mock API client for the datasource
        client = self._get_source_client()

        if since:
            # Incremental indexing - get only modified items
            return client.get_modified_items(since=since)
        else:
            # Full indexing - get all items
            return client.get_all_items()

    def transform(self, data: Sequence[dict]) -> List[DocumentDefinition]:
        """Transform source data to Glean document format.

        Args:
            data: The source data to transform.

        Returns:
            A list of DocumentDefinition objects ready for indexing.
        """
        logger.info(f"Transforming {len(data)} items to Glean document format")

        documents = []

        # Process data in batches for memory efficiency
        for batch in BatchProcessor(data, batch_size=100):
            for item in batch:
                doc = DocumentDefinition(
                    id=item["id"],
                    title=item["title"],
                    content=item.get("content"),
                    url=item.get("url"),
                    container_id=item.get("container_id"),
                    created_at=item.get("created_at"),
                    updated_at=item.get("updated_at"),
                    metadata={
                        "source": self.name,
                        "type": item.get("type", "document"),
                        "author": item.get("author"),
                        "tags": item.get("tags", []),
                    },
                )
                documents.append(doc)

        return documents

    def _get_source_client(self):
        """Get the API client for the datasource.

        Returns:
            A mock API client for the datasource.
        """
        return MockDataSourceClient()

