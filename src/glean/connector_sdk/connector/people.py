"""Example people connector implementation."""

import logging
from typing import List, Optional, Sequence

from glean.connector_sdk.connector.base_people_connector import BasePeopleConnector
from glean.connector_sdk.examples.mock_clients import MockPeopleClient
from glean.connector_sdk.models import EmployeeDefinition
from glean.connector_sdk.utils import BatchProcessor


logger = logging.getLogger(__name__)


class MyPeopleConnector(BasePeopleConnector):
    """Example people connector implementation."""
    
    name = "my_people_connector"
    
    def get_people_data(self, since: Optional[str] = None) -> Sequence[dict]:
        """Get people data from the source.
        
        Args:
            since: If provided, only get data modified since this timestamp.
            
        Returns:
            A sequence of dictionaries containing the source people data.
        """
        logger.info(f"Fetching people data from source{' since ' + since if since else ''}")
        
        # Mock API client for the people source
        client = self._get_source_client()
        
        if since:
            # Incremental indexing - get only modified people
            return client.get_modified_people(since=since)
        else:
            # Full indexing - get all people
            return client.get_all_people()
    
    def transform_people(self, data: Sequence[dict]) -> List[EmployeeDefinition]:
        """Transform source data to Glean employee format.
        
        Args:
            data: The source people data to transform.
            
        Returns:
            A list of EmployeeDefinition objects ready for indexing.
        """
        logger.info(f"Transforming {len(data)} people to Glean employee format")
        
        employees = []
        
        # Process data in batches for memory efficiency
        for batch in BatchProcessor(data, batch_size=100):
            for item in batch:
                employee = EmployeeDefinition(
                    id=item["id"],
                    name=item["name"],
                    email=item.get("email"),
                    manager_id=item.get("manager_id"),
                    department=item.get("department"),
                    title=item.get("title"),
                    start_date=item.get("start_date"),
                    location=item.get("location"),
                    metadata={
                        "source": self.name,
                    }
                )
                employees.append(employee)
        
        return employees
    
    def _get_source_client(self):
        """Get the API client for the people source.
        
        Returns:
            A mock API client for the people source.
        """
        return MockPeopleClient() 