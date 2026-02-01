"""Tests for async streaming base classes."""

import asyncio
from typing import AsyncGenerator, Sequence
from unittest.mock import MagicMock, patch

import pytest

from glean.api_client.models import DocumentDefinition
from glean.indexing.connectors.async_streaming import (
    AsyncBaseStreamingDataClient,
    AsyncBaseStreamingDatasourceConnector,
    AsyncStreamingDataClient,
    AsyncStreamingDatasourceConnector,
)


class DummyAsyncDataClient(AsyncBaseStreamingDataClient[dict]):
    """Test implementation of async data client."""

    def __init__(self, items: list[dict] | None = None):
        if items is not None:
            self.items = items
        else:
            self.items = [
                {"id": f"doc-{i}", "title": f"Document {i}", "content": f"Content {i}"}
                for i in range(5)
            ]

    async def get_source_data(self, **kwargs) -> AsyncGenerator[dict, None]:
        for item in self.items:
            yield item


class DummyAsyncConnector(AsyncBaseStreamingDatasourceConnector[dict]):
    """Test implementation of async connector."""

    configuration = MagicMock()

    def transform(self, data: Sequence[dict]) -> Sequence[DocumentDefinition]:
        return [
            DocumentDefinition(
                id=item["id"],
                title=item["title"],
                container="test",
                datasource="test_datasource",
                viewURL=f"https://example.com/{item['id']}",
            )
            for item in data
        ]


class TestAsyncBaseStreamingDataClient:
    """Tests for AsyncBaseStreamingDataClient."""

    def test_abstract_cannot_instantiate(self):
        """Test that base class cannot be instantiated directly."""
        with pytest.raises(TypeError):
            AsyncBaseStreamingDataClient()  # type: ignore

    def test_concrete_implementation_works(self):
        """Test that concrete implementation can be instantiated."""
        client = DummyAsyncDataClient()
        assert client is not None

    @pytest.mark.asyncio
    async def test_get_source_data_yields_items(self):
        """Test that get_source_data yields all items."""
        client = DummyAsyncDataClient()
        items = [item async for item in client.get_source_data()]
        assert len(items) == 5
        assert items[0]["id"] == "doc-0"
        assert items[4]["id"] == "doc-4"

    @pytest.mark.asyncio
    async def test_get_source_data_empty(self):
        """Test that empty data client yields nothing."""
        client = DummyAsyncDataClient(items=[])
        items = [item async for item in client.get_source_data()]
        assert len(items) == 0


class TestAsyncBaseStreamingDatasourceConnector:
    """Tests for AsyncBaseStreamingDatasourceConnector."""

    def test_init_sets_async_client(self):
        """Test that init properly sets the async data client."""
        client = DummyAsyncDataClient()
        connector = DummyAsyncConnector("test", client)
        assert connector.async_data_client is client
        assert connector.name == "test"
        assert connector.batch_size == 1000

    def test_generate_upload_id(self):
        """Test that upload ID is generated and cached."""
        connector = DummyAsyncConnector("test", DummyAsyncDataClient())
        upload_id1 = connector.generate_upload_id()
        upload_id2 = connector.generate_upload_id()
        assert upload_id1 == upload_id2
        assert len(upload_id1) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_get_data_async_yields_items(self):
        """Test that get_data_async yields all items from client."""
        connector = DummyAsyncConnector("test", DummyAsyncDataClient())
        items = [item async for item in connector.get_data_async()]
        assert len(items) == 5

    def test_transform_maps_to_document_definition(self):
        """Test that transform produces DocumentDefinition objects."""
        connector = DummyAsyncConnector("test", DummyAsyncDataClient())
        data = [{"id": "doc-0", "title": "Test", "content": "Content"}]
        docs = connector.transform(data)
        assert len(docs) == 1
        assert isinstance(docs[0], DocumentDefinition)
        assert docs[0].id == "doc-0"

    @pytest.mark.asyncio
    async def test_index_data_async_batches_and_uploads(self):
        """Test that index_data_async batches and uploads correctly."""
        client = DummyAsyncDataClient()
        connector = DummyAsyncConnector("test", client)
        connector.batch_size = 2

        with patch(
            "glean.indexing.connectors.async_streaming.api_client"
        ) as mock_api_client:
            bulk_index = mock_api_client().__enter__().indexing.documents.bulk_index
            await connector.index_data_async()

            # 5 items with batch_size=2 should create 3 batches
            assert bulk_index.call_count == 3

            # Check first batch
            first_call = bulk_index.call_args_list[0][1]
            assert first_call["is_first_page"] is True
            assert first_call["is_last_page"] is False
            assert len(first_call["documents"]) == 2

            # Check last batch
            last_call = bulk_index.call_args_list[2][1]
            assert last_call["is_first_page"] is False
            assert last_call["is_last_page"] is True
            assert len(last_call["documents"]) == 1

    @pytest.mark.asyncio
    async def test_index_data_async_empty(self):
        """Test that empty data results in no uploads."""
        client = DummyAsyncDataClient(items=[])
        connector = DummyAsyncConnector("test", client)

        with patch(
            "glean.indexing.connectors.async_streaming.api_client"
        ) as mock_api_client:
            bulk_index = mock_api_client().__enter__().indexing.documents.bulk_index
            await connector.index_data_async()
            assert bulk_index.call_count == 0

    @pytest.mark.asyncio
    async def test_index_data_async_force_restart(self):
        """Test that force_restart sets forceRestartUpload on first batch."""
        client = DummyAsyncDataClient()
        connector = DummyAsyncConnector("test", client)
        connector.batch_size = 2

        with patch(
            "glean.indexing.connectors.async_streaming.api_client"
        ) as mock_api_client:
            bulk_index = mock_api_client().__enter__().indexing.documents.bulk_index
            await connector.index_data_async(force_restart=True)

            # First batch should have forceRestartUpload
            first_call = bulk_index.call_args_list[0][1]
            assert first_call["forceRestartUpload"] is True

            # Subsequent batches should not
            second_call = bulk_index.call_args_list[1][1]
            assert "forceRestartUpload" not in second_call

    @pytest.mark.asyncio
    async def test_index_data_async_error_handling(self):
        """Test that errors during indexing are propagated."""
        client = DummyAsyncDataClient()
        connector = DummyAsyncConnector("test", client)

        with patch(
            "glean.indexing.connectors.async_streaming.api_client"
        ) as mock_api_client:
            bulk_index = mock_api_client().__enter__().indexing.documents.bulk_index
            bulk_index.side_effect = Exception("upload failed")

            with pytest.raises(Exception, match="upload failed"):
                await connector.index_data_async()

    def test_sync_fallback_get_data(self):
        """Test that sync get_data() works as fallback."""
        connector = DummyAsyncConnector("test", DummyAsyncDataClient())
        data = connector.get_data()
        assert len(data) == 5

    def test_sync_fallback_index_data(self):
        """Test that sync index_data() works as fallback."""
        connector = DummyAsyncConnector("test", DummyAsyncDataClient())
        connector.batch_size = 10

        with patch(
            "glean.indexing.connectors.async_streaming.api_client"
        ) as mock_api_client:
            bulk_index = mock_api_client().__enter__().indexing.documents.bulk_index
            connector.index_data()
            assert bulk_index.call_count == 1


class TestAliases:
    """Test that convenience aliases work."""

    def test_async_streaming_data_client_alias(self):
        """Test AsyncStreamingDataClient is alias for AsyncBaseStreamingDataClient."""
        assert AsyncStreamingDataClient is AsyncBaseStreamingDataClient

    def test_async_streaming_datasource_connector_alias(self):
        """Test AsyncStreamingDatasourceConnector is alias for AsyncBaseStreamingDatasourceConnector."""
        assert AsyncStreamingDatasourceConnector is AsyncBaseStreamingDatasourceConnector
