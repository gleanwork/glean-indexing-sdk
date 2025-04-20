"""Testing utilities for the Glean Connector SDK."""

import logging
from typing import Any, Callable, Dict, List, Optional, Sequence, Type
import json

from glean.connector_sdk.connector.base_connector import BaseConnector
from glean.connector_sdk.connector.base_datasource_connector import BaseDatasourceConnector
from glean.connector_sdk.connector.base_people_connector import BasePeopleConnector
from glean.connector_sdk.models import DocumentDefinition, EmployeeDefinition


logger = logging.getLogger(__name__)


class MockDataSource:
    """Mock data source for testing."""
    
    def __init__(
        self,
        all_items: Optional[List[Dict[str, Any]]] = None,
        modified_items: Optional[List[Dict[str, Any]]] = None,
    ):
        """Initialize the MockDataSource.
        
        Args:
            all_items: Items to return for get_all_items.
            modified_items: Items to return for get_modified_items.
        """
        self.all_items = all_items or []
        self.modified_items = modified_items or []
    
    def get_all_items(self) -> List[Dict[str, Any]]:
        """Get all items.
        
        Returns:
            A list of all items.
        """
        logger.info(f"MockDataSource.get_all_items() returning {len(self.all_items)} items")
        return self.all_items
    
    def get_modified_items(self, since: str) -> List[Dict[str, Any]]:
        """Get modified items.
        
        Args:
            since: Timestamp to filter by.
            
        Returns:
            A list of modified items.
        """
        logger.info(f"MockDataSource.get_modified_items(since={since}) returning {len(self.modified_items)} items")
        return self.modified_items


class ResponseValidator:
    """Validator for connector responses."""
    
    def __init__(self):
        """Initialize the ResponseValidator."""
        self.documents_posted: List[DocumentDefinition] = []
        self.employees_posted: List[EmployeeDefinition] = []
    
    def assert_documents_posted(self, count: Optional[int] = None) -> None:
        """Assert that documents were posted.
        
        Args:
            count: Optional expected count of documents.
        """
        if count is not None:
            assert len(self.documents_posted) == count, (
                f"Expected {count} documents to be posted, but got {len(self.documents_posted)}"
            )
        else:
            assert len(self.documents_posted) > 0, "No documents were posted"
        
        logger.info(f"Validated {len(self.documents_posted)} documents posted")
    
    def assert_employees_posted(self, count: Optional[int] = None) -> None:
        """Assert that employees were posted.
        
        Args:
            count: Optional expected count of employees.
        """
        if count is not None:
            assert len(self.employees_posted) == count, (
                f"Expected {count} employees to be posted, but got {len(self.employees_posted)}"
            )
        else:
            assert len(self.employees_posted) > 0, "No employees were posted"
        
        logger.info(f"Validated {len(self.employees_posted)} employees posted")
    
    def reset(self) -> None:
        """Reset the validator state."""
        self.documents_posted.clear()
        self.employees_posted.clear()


class MockGleanClient:
    """Mock Glean API client for testing."""
    
    def __init__(self, validator: ResponseValidator):
        """Initialize the MockGleanClient.
        
        Args:
            validator: Validator to record posted items.
        """
        self.validator = validator
    
    def batch_index_documents(self, datasource: str, documents: List[DocumentDefinition]) -> None:
        """Mock method for indexing documents.
        
        Args:
            datasource: The datasource name.
            documents: The documents to index.
        """
        logger.info(f"Mock indexing {len(documents)} documents to datasource '{datasource}'")
        self.validator.documents_posted.extend(documents)
    
    def bulk_index_employees(self, employees: List[EmployeeDefinition]) -> None:
        """Mock method for indexing employees.
        
        Args:
            employees: The employees to index.
        """
        logger.info(f"Mock indexing {len(employees)} employees")
        self.validator.employees_posted.extend(employees)


class ConnectorTestHarness:
    """Test harness for connectors."""
    
    def __init__(self, connector: BaseConnector):
        """Initialize the ConnectorTestHarness.
        
        Args:
            connector: The connector to test.
        """
        self.connector = connector
        self.validator = ResponseValidator()
        
        # Replace the connector's get_client method
        self._original_get_client = connector.get_client
        connector.get_client = lambda: MockGleanClient(self.validator)
    
    def run(self) -> None:
        """Run the connector."""
        logger.info(f"Running test harness for connector '{self.connector.name}'")
        
        # Reset validator
        self.validator.reset()
        
        # Run the connector based on its type
        if isinstance(self.connector, BaseDatasourceConnector):
            self.connector.index_data()
        elif isinstance(self.connector, BasePeopleConnector):
            self.connector.index_people()
        else:
            raise ValueError(f"Unsupported connector type: {type(self.connector)}")
    
    def __del__(self) -> None:
        """Restore the connector's get_client method."""
        if hasattr(self, '_original_get_client') and hasattr(self, 'connector'):
            self.connector.get_client = self._original_get_client 