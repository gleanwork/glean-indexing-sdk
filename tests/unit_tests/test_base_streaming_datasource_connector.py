from unittest.mock import MagicMock, patch

import pytest

from glean.api_client.models import DocumentDefinition
from glean.indexing.connectors import BaseStreamingDataClient, BaseStreamingDatasourceConnector
from glean.indexing.models import ConnectorOptions


class DummyStreamingDataClient(BaseStreamingDataClient[dict]):
    def get_source_data(self, **kwargs):
        for i in range(5):
            yield {
                "id": f"doc-{i}",
                "title": f"Document {i}",
                "content": f"Content {i}",
                "url": f"https://example.com/{i}",
                "created_at": 1672531200,
                "updated_at": 1672617600,
                "author": {"id": "user@example.com"},
                "type": "document",
                "tags": ["example"],
                "datasource": "test_datasource",
            }


class DummyStreamingConnector(BaseStreamingDatasourceConnector[dict]):
    configuration = MagicMock()

    def transform(self, data):
        return [
            DocumentDefinition(
                **{
                    "id": item["id"],
                    "title": item["title"],
                    "content": item["content"],
                    "url": item["url"],
                    "created_at": item["created_at"],
                    "updated_at": item["updated_at"],
                    "author": item["author"],
                    "type": item["type"],
                    "tags": item["tags"],
                    "datasource": item["datasource"],
                }
            )
            for item in data
        ]


def test_get_data_streams_all():
    client = DummyStreamingDataClient()
    connector = DummyStreamingConnector("test_stream", client)
    data = list(connector.get_data())
    assert len(data) == 5
    assert data[0]["id"] == "doc-0"


def test_transform_maps_to_document_definition():
    connector = DummyStreamingConnector("test_stream", DummyStreamingDataClient())
    data = list(DummyStreamingDataClient().get_source_data())
    docs = connector.transform(data)
    assert all(isinstance(d, DocumentDefinition) for d in docs)
    assert docs[0].id == "doc-0"


def test_index_data_batches_and_uploads():
    client = DummyStreamingDataClient()
    connector = DummyStreamingConnector("test_stream", client)
    connector.batch_size = 2
    with patch(
        "glean.indexing.connectors.base_streaming_datasource_connector.api_client"
    ) as api_client:
        bulk_index = api_client().__enter__().indexing.documents.bulk_index
        connector.index_data()
        assert bulk_index.call_count == 3
        for call in bulk_index.call_args_list:
            _, kwargs = call
            assert "documents" in kwargs
            assert "is_first_page" in kwargs
            assert "is_last_page" in kwargs


def test_index_data_empty():
    class EmptyClient(BaseStreamingDataClient[dict]):
        def get_source_data(self, **kwargs):
            yield from []

    connector = DummyStreamingConnector("test_stream", EmptyClient())
    with patch(
        "glean.indexing.connectors.base_streaming_datasource_connector.api_client"
    ) as api_client:
        bulk_index = api_client().__enter__().indexing.documents.bulk_index
        connector.index_data()
        assert bulk_index.call_count == 0


def test_index_data_error_handling():
    client = DummyStreamingDataClient()
    connector = DummyStreamingConnector("test_stream", client)
    with patch(
        "glean.indexing.connectors.base_streaming_datasource_connector.api_client"
    ) as api_client:
        bulk_index = api_client().__enter__().indexing.documents.bulk_index
        bulk_index.side_effect = Exception("upload failed")
        with pytest.raises(Exception):
            connector.index_data()


def test_force_restart_upload():
    """Test that force_restart option sets force_restart_upload on first batch."""
    client = DummyStreamingDataClient()
    connector = DummyStreamingConnector("test_stream", client)
    connector.batch_size = 2

    with patch(
        "glean.indexing.connectors.base_streaming_datasource_connector.api_client"
    ) as api_client:
        bulk_index = api_client().__enter__().indexing.documents.bulk_index
        connector.index_data(options=ConnectorOptions(force_restart=True))

        assert bulk_index.call_count == 3

        # First call should have force_restart_upload=True
        first_call_kwargs = bulk_index.call_args_list[0][1]
        assert first_call_kwargs["force_restart_upload"] is True
        assert first_call_kwargs["is_first_page"] is True
        assert first_call_kwargs["is_last_page"] is False

        # Subsequent calls should have force_restart_upload=None
        second_call_kwargs = bulk_index.call_args_list[1][1]
        assert second_call_kwargs["force_restart_upload"] is None
        assert second_call_kwargs["is_first_page"] is False
        assert second_call_kwargs["is_last_page"] is False

        third_call_kwargs = bulk_index.call_args_list[2][1]
        assert third_call_kwargs["force_restart_upload"] is None
        assert third_call_kwargs["is_first_page"] is False
        assert third_call_kwargs["is_last_page"] is True


def test_normal_upload_no_force_restart():
    """Test that normal upload does not set force_restart_upload."""
    client = DummyStreamingDataClient()
    connector = DummyStreamingConnector("test_stream", client)
    connector.batch_size = 5

    with patch(
        "glean.indexing.connectors.base_streaming_datasource_connector.api_client"
    ) as api_client:
        bulk_index = api_client().__enter__().indexing.documents.bulk_index
        connector.index_data()

        assert bulk_index.call_count == 1

        call_kwargs = bulk_index.call_args[1]
        assert call_kwargs["force_restart_upload"] is None
        assert call_kwargs["is_first_page"] is True
        assert call_kwargs["is_last_page"] is True


def test_disable_stale_deletion_check_on_last_page_only():
    """Test that disable_stale_document_deletion_check is set only on the last batch."""
    client = DummyStreamingDataClient()
    connector = DummyStreamingConnector("test_stream", client)
    connector.batch_size = 2

    with patch(
        "glean.indexing.connectors.base_streaming_datasource_connector.api_client"
    ) as api_client:
        bulk_index = api_client().__enter__().indexing.documents.bulk_index
        connector.index_data(options=ConnectorOptions(disable_stale_deletion_check=True))

        assert bulk_index.call_count == 3

        first_call_kwargs = bulk_index.call_args_list[0][1]
        assert first_call_kwargs["disable_stale_document_deletion_check"] is None

        second_call_kwargs = bulk_index.call_args_list[1][1]
        assert second_call_kwargs["disable_stale_document_deletion_check"] is None

        last_call_kwargs = bulk_index.call_args_list[2][1]
        assert last_call_kwargs["disable_stale_document_deletion_check"] is True
