"""Unit tests for the connectors."""

import unittest
from glean.connector_sdk.connector import MyDatasourceConnector, MyPeopleConnector
from glean.connector_sdk.models import DocumentDefinition, EmployeeDefinition, IndexingMode
from glean.connector_sdk.testing import ConnectorTestHarness, MockDataSource, ResponseValidator


class TestDatasourceConnector:
    """Tests for the datasource connector."""
    
    def test_index_data_full(self):
        """Test that the datasource connector can perform a full indexing."""
        # Create a connector
        connector = MyDatasourceConnector()
        
        # Create a test harness
        harness = ConnectorTestHarness(connector)
        
        # Run the connector
        harness.run()
        
        # Validate the results
        harness.validator.assert_documents_posted(count=5)


class TestPeopleConnector:
    """Tests for the people connector."""
    
    def test_index_people_full(self):
        """Test that the people connector can perform a full indexing."""
        # Create a connector
        connector = MyPeopleConnector()
        
        # Create a test harness
        harness = ConnectorTestHarness(connector)
        
        # Run the connector
        harness.run()
        
        # Validate the results
        harness.validator.assert_employees_posted(count=5)
    
    def test_index_people_incremental(self):
        """Test that the people connector can perform an incremental indexing."""
        # Create a connector
        connector = MyPeopleConnector()
        
        # Create a test harness
        harness = ConnectorTestHarness(connector)
        
        # Run the connector in incremental mode
        connector.index_people(mode=IndexingMode.INCREMENTAL)
        
        # Validate the results
        harness.validator.assert_employees_posted(count=1)


class TestMocks:
    """Tests for the testing utilities."""
    
    def test_mock_data_source(self):
        """Test that the MockDataSource works as expected."""
        # Create a mock data source with sample data
        all_items = [{"id": "1", "title": "Test Document"}]
        modified_items = [{"id": "2", "title": "Modified Document"}]
        
        mock_source = MockDataSource(all_items=all_items, modified_items=modified_items)
        
        # Verify the mock returns the expected data
        assert mock_source.get_all_items() == all_items
        assert mock_source.get_modified_items(since="2023-01-01") == modified_items
    
    def test_response_validator(self):
        """Test that the ResponseValidator works as expected."""
        # Create a validator
        validator = ResponseValidator()
        
        # Add some test data
        validator.documents_posted = [
            DocumentDefinition(id="1", title="Document 1"),
            DocumentDefinition(id="2", title="Document 2"),
        ]
        
        validator.employees_posted = [
            EmployeeDefinition(id="1", name="Employee 1"),
        ]
        
        # Validate counts
        validator.assert_documents_posted(count=2)
        validator.assert_employees_posted(count=1)
        
        # Test reset
        validator.reset()
        
        # Verify reset worked
        assert len(validator.documents_posted) == 0
        assert len(validator.employees_posted) == 0 