"""Base class for people connectors."""

import logging
from abc import abstractmethod
from typing import List, Optional, Sequence

from glean.connector_sdk.connector.base_connector import BaseConnector
from glean.connector_sdk.models import EmployeeDefinition, IndexingMode


logger = logging.getLogger(__name__)


class BasePeopleConnector(BaseConnector):
    """Base class for people connectors."""

    def index_people(self, mode: IndexingMode = IndexingMode.FULL) -> None:
        """Index people data to Glean.

        Args:
            mode: The indexing mode to use (FULL or INCREMENTAL).
        """
        logger.info(f"Starting {mode.name.lower()} people indexing for '{self.name}'")

        since = None
        if mode == IndexingMode.INCREMENTAL:
            # In a real implementation, this would get the last indexing timestamp
            since = "2023-01-01T00:00:00Z"

        # Get people data from source
        data = self.get_people_data(since=since)
        logger.info(f"Retrieved {len(data)} people from source")

        # Transform to Glean employee format
        employees = self.transform_people(data)
        logger.info(f"Transformed {len(employees)} employees")

        # Post to Glean index
        self.post_to_index(employees)
        logger.info(f"Indexed {len(employees)} employees to Glean")

    @abstractmethod
    def get_people_data(self, since: Optional[str] = None) -> Sequence[dict]:
        """Get people data from the source.

        Args:
            since: If provided, only get data modified since this timestamp.

        Returns:
            A sequence of dictionaries containing the source people data.
        """
        pass

    @abstractmethod
    def transform_people(self, data: Sequence[dict]) -> List[EmployeeDefinition]:
        """Transform source data to Glean employee format.

        Args:
            data: The source people data to transform.

        Returns:
            A list of EmployeeDefinition objects ready for indexing.
        """
        pass

    def post_to_index(self, employees: List[EmployeeDefinition]) -> None:
        """Post employees to the Glean index.

        Args:
            employees: The employees to index.
        """
        # In a real implementation, this would use the Glean API client
        client = self.get_client()
        client.bulk_index_employees(employees=employees) 