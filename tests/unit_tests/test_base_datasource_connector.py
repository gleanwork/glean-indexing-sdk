"""Tests for BaseDatasourceConnector."""

from typing import List, Sequence
from unittest.mock import Mock, patch

from glean.api_client.models import ContentDefinition, DocumentDefinition
from glean.indexing.connectors import BaseConnectorDataClient, BaseDatasourceConnector
from glean.indexing.models import CustomDatasourceConfig


class MockDataClient(BaseConnectorDataClient[dict]):
    """Mock data client for testing."""

    def __init__(self, data: List[dict]):
        self.data = data

    def get_source_data(self, since=None) -> Sequence[dict]:
        return self.data


class TestDatasourceConnector(BaseDatasourceConnector[dict]):
    """Test implementation of BaseDatasourceConnector."""

    configuration: CustomDatasourceConfig = CustomDatasourceConfig(
        name="test_connector",
        display_name="Test Connector",
        url_regex=r"https://test\.example\.com/.*",
        trust_url_regex_for_view_activity=True,
    )

    def transform(self, data: Sequence[dict]) -> List[DocumentDefinition]:
        documents = []
        for item in data:
            document = DocumentDefinition(
                id=item["id"],
                title=item["title"],
                datasource=self.name,
                view_url=item["url"],
                body=ContentDefinition(mime_type="text/plain", text_content=item["content"]),
            )
            documents.append(document)
        return documents


class TestBaseDatasourceConnector:
    """Test cases for BaseDatasourceConnector."""

    def test_connector_initialization(self):
        """Test that connector initializes correctly."""
        data_client = MockDataClient([])
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)

        assert connector.name == "test_connector"
        assert connector.display_name == "Test Connector"
        assert connector.data_client == data_client
        assert connector.batch_size == 1000

    def test_config_property(self):
        """Test that config property includes name and display_name."""
        data_client = MockDataClient([])
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)

        config = connector.configuration
        assert config.name == "test_connector"
        assert config.display_name == "Test Connector"
        assert config.url_regex == r"https://test\.example\.com/.*"
        assert config.trust_url_regex_for_view_activity is True

    @patch("glean.indexing.connectors.base_datasource_connector.api_client")
    def test_configure_datasource(self, mock_api_client):
        """Test datasource configuration."""
        mock_client = Mock()
        mock_api_client.return_value.__enter__.return_value = mock_client

        data_client = MockDataClient([])
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)

        connector.configure_datasource()

        mock_client.indexing.datasources.add.assert_called_once()
        call_args = mock_client.indexing.datasources.add.call_args[1]
        assert call_args["name"] == "test_connector"
        assert call_args["display_name"] == "Test Connector"

    def test_get_data(self):
        """Test data retrieval from data client."""
        test_data = [
            {
                "id": "1",
                "title": "Test Doc",
                "content": "Content",
                "url": "https://test.example.com/1",
            }
        ]
        data_client = MockDataClient(test_data)
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)

        result = connector.get_data()
        assert result == test_data

    def test_transform(self):
        """Test data transformation."""
        test_data = [
            {
                "id": "1",
                "title": "Test Doc",
                "content": "Content",
                "url": "https://test.example.com/1",
            }
        ]
        data_client = MockDataClient(test_data)
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)

        documents = connector.transform(test_data)

        assert len(documents) == 1
        doc = documents[0]
        assert doc.id == "1"
        assert doc.title == "Test Doc"
        assert doc.datasource == "test_connector"
        assert doc.view_url == "https://test.example.com/1"
        assert doc.body and doc.body.text_content == "Content"

    def test_get_last_crawl_timestamp(self):
        """Test that default timestamp is None."""
        data_client = MockDataClient([])
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)

        timestamp = connector._get_last_crawl_timestamp()
        assert timestamp is None

    @patch("glean.indexing.connectors.base_datasource_connector.api_client")
    def test_force_restart_upload(self, mock_api_client):
        """Test that force_restart parameter sets forceRestartUpload on first batch."""
        mock_client = Mock()
        mock_api_client.return_value.__enter__.return_value = mock_client

        test_data = [
            {
                "id": "1",
                "title": "Test Doc 1",
                "content": "Content 1",
                "url": "https://test.example.com/1",
            },
            {
                "id": "2",
                "title": "Test Doc 2",
                "content": "Content 2",
                "url": "https://test.example.com/2",
            },
        ]
        data_client = MockDataClient(test_data)
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)
        connector.batch_size = 1

        connector.index_data(force_restart=True)

        # Should be called twice (one batch per document)
        assert mock_client.indexing.documents.bulk_index.call_count == 2

        # First call should have forceRestartUpload=True
        first_call_kwargs = mock_client.indexing.documents.bulk_index.call_args_list[0][1]
        assert first_call_kwargs["forceRestartUpload"] is True
        assert first_call_kwargs["is_first_page"] is True
        assert first_call_kwargs["is_last_page"] is False

        # Second call should NOT have forceRestartUpload
        second_call_kwargs = mock_client.indexing.documents.bulk_index.call_args_list[1][1]
        assert "forceRestartUpload" not in second_call_kwargs
        assert second_call_kwargs["is_first_page"] is False
        assert second_call_kwargs["is_last_page"] is True

    @patch("glean.indexing.connectors.base_datasource_connector.api_client")
    def test_normal_upload_no_force_restart(self, mock_api_client):
        """Test that normal upload does not include forceRestartUpload parameter."""
        mock_client = Mock()
        mock_api_client.return_value.__enter__.return_value = mock_client

        test_data = [
            {
                "id": "1",
                "title": "Test Doc",
                "content": "Content",
                "url": "https://test.example.com/1",
            }
        ]
        data_client = MockDataClient(test_data)
        connector = TestDatasourceConnector(name="test_connector", data_client=data_client)

        connector.index_data(force_restart=False)

        # Should be called once
        assert mock_client.indexing.documents.bulk_index.call_count == 1

        # Should NOT have forceRestartUpload parameter
        call_kwargs = mock_client.indexing.documents.bulk_index.call_args[1]
        assert "forceRestartUpload" not in call_kwargs
        assert call_kwargs["is_first_page"] is True
        assert call_kwargs["is_last_page"] is True
