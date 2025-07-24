from unittest.mock import MagicMock, patch

import pytest

from glean.api_client.models import DocumentDefinition
from glean.indexing.connectors import BaseStreamingDataClient, BaseStreamingDatasourceConnector


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
            if False:
                yield

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


def test_index_data_empty_dataset():
    class EmptyStreamingDataClient(BaseStreamingDataClient[dict]):
        def get_source_data(self, **kwargs):
            return
            yield  # This is unreachable but makes it a generator

    client = EmptyStreamingDataClient()
    connector = DummyStreamingConnector("test_stream", client)
    with patch(
        "glean.indexing.connectors.base_streaming_datasource_connector.api_client"
    ) as api_client:
        bulk_index = api_client().__enter__().indexing.documents.bulk_index
        connector.index_data()
        assert bulk_index.call_count == 0


def test_index_data_api_error():
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
    """Test that force_restart parameter sets forceRestartUpload on first batch."""
    client = DummyStreamingDataClient()
    connector = DummyStreamingConnector("test_stream", client)
    connector.batch_size = 2

    with patch(
        "glean.indexing.connectors.base_streaming_datasource_connector.api_client"
    ) as api_client:
        bulk_index = api_client().__enter__().indexing.documents.bulk_index
        connector.index_data(force_restart=True)

        assert bulk_index.call_count == 3

        # First call should have forceRestartUpload=True
        first_call_kwargs = bulk_index.call_args_list[0][1]
        assert first_call_kwargs["forceRestartUpload"] is True
        assert first_call_kwargs["is_first_page"] is True
        assert first_call_kwargs["is_last_page"] is False

        # Subsequent calls should NOT have forceRestartUpload
        second_call_kwargs = bulk_index.call_args_list[1][1]
        assert "forceRestartUpload" not in second_call_kwargs
        assert second_call_kwargs["is_first_page"] is False
        assert second_call_kwargs["is_last_page"] is False

        third_call_kwargs = bulk_index.call_args_list[2][1]
        assert "forceRestartUpload" not in third_call_kwargs
        assert third_call_kwargs["is_first_page"] is False
        assert third_call_kwargs["is_last_page"] is True


def test_normal_upload_no_force_restart():
    """Test that normal upload does not include forceRestartUpload parameter."""
    client = DummyStreamingDataClient()
    connector = DummyStreamingConnector("test_stream", client)
    connector.batch_size = 5

    with patch(
        "glean.indexing.connectors.base_streaming_datasource_connector.api_client"
    ) as api_client:
        bulk_index = api_client().__enter__().indexing.documents.bulk_index
        connector.index_data(force_restart=False)

        assert bulk_index.call_count == 1

        # Should NOT have forceRestartUpload parameter
        call_kwargs = bulk_index.call_args[1]
        assert "forceRestartUpload" not in call_kwargs
        assert call_kwargs["is_first_page"] is True
        assert call_kwargs["is_last_page"] is True
