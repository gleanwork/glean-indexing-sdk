"""Integration tests for the example connectors."""

import pytest

from glean.connector_sdk.connector import MyDatasourceConnector, MyPeopleConnector
from glean.connector_sdk.models import IndexingMode
from glean.connector_sdk.testing import ConnectorTestHarness


class TestExampleConnectors:
    """Integration tests for example connectors."""
    
    def test_datasource_example(self):
        """Test that the datasource example runs without errors."""
        # Create a connector
        connector = MyDatasourceConnector()
        
        # Create a test harness
        harness = ConnectorTestHarness(connector)
        
        # Run the connector in full mode
        connector.index_data(mode=IndexingMode.FULL)
        
        # Validate something was posted
        harness.validator.assert_documents_posted()
        
    def test_people_example(self):
        """Test that the people example runs without errors."""
        # Create a connector
        connector = MyPeopleConnector()
        
        # Create a test harness
        harness = ConnectorTestHarness(connector)
        
        # Run the connector in incremental mode
        connector.index_people(mode=IndexingMode.INCREMENTAL)
        
        # Validate something was posted
        harness.validator.assert_employees_posted() 