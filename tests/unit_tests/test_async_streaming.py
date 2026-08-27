"""Tests for async streaming base classes."""

import asyncio
import threading
import time
from typing import AsyncGenerator, Sequence
from unittest import TestCase
from unittest.mock import MagicMock, patch

import pytest

from glean.api_client.models import DocumentDefinition
from glean.indexing.connectors import (
    BaseAsyncStreamingDataClient,
    BaseAsyncStreamingDatasourceConnector,
)
from glean.indexing.models import ConnectorOptions
from glean.indexing.observability import InMemoryMetricsProvider
from glean.indexing.push import PushUploader


class DummyAsyncDataClient(BaseAsyncStreamingDataClient[dict]):
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


class DummyAsyncConnector(BaseAsyncStreamingDatasourceConnector[dict]):
    """Test implementation of async connector."""

    configuration = MagicMock()

    def transform(self, data: Sequence[dict]) -> Sequence[DocumentDefinition]:
        return [
            DocumentDefinition(
                id=item["id"],
                title=item["title"],
                container="test",
                datasource="test_datasource",
                view_url=f"https://example.com/{item['id']}",
            )
            for item in data
        ]


class TestBaseAsyncStreamingDataClient:
    """Tests for BaseAsyncStreamingDataClient."""

    def test_abstract_cannot_instantiate(self):
        """Test that base class cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseAsyncStreamingDataClient()  # type: ignore

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


class TestBaseAsyncStreamingDatasourceConnector:
    """Tests for BaseAsyncStreamingDatasourceConnector."""

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

        with patch("glean.indexing.push.uploader.api_client") as mock_api_client:
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
        """Test that empty data completes one observable lifecycle without uploads."""
        client = DummyAsyncDataClient(items=[])
        connector = DummyAsyncConnector("test", client)

        with (
            TestCase().assertLogs(
                "glean.indexing.observability.observability", level="INFO"
            ) as captured,
            patch("glean.indexing.push.uploader.api_client") as mock_api_client,
        ):
            bulk_index = mock_api_client().__enter__().indexing.documents.bulk_index
            await connector.index_data_async()

        assert bulk_index.call_count == 0
        operations = [getattr(record, "operation", None) for record in captured.records]
        assert operations.count("crawl_started") == 1
        assert operations.count("crawl_completed") == 1
        assert (
            connector.observability.get_metrics_summary().items()
            >= {
                "items_fetched": 0,
                "documents_transformed": 0,
                "documents_indexed": 0,
            }.items()
        )

    @pytest.mark.asyncio
    async def test_index_data_async_uploads_middle_pages_concurrently(self):
        client = DummyAsyncDataClient(
            items=[
                {"id": f"doc-{i}", "title": f"Doc {i}", "content": f"Content {i}"}
                for i in range(10)
            ]
        )
        connector = DummyAsyncConnector("test", client)
        connector.batch_size = 2
        barrier = threading.Barrier(2)
        lock = threading.Lock()
        active_uploads = 0
        max_active_uploads = 0

        def upload_batch(*, batch_index=0, is_first_page, is_last_page, **kwargs):
            nonlocal active_uploads, max_active_uploads
            if is_first_page or is_last_page:
                return
            with lock:
                active_uploads += 1
                max_active_uploads = max(max_active_uploads, active_uploads)
            if batch_index in {1, 2}:
                barrier.wait(timeout=1)
            time.sleep(0.01)
            with lock:
                active_uploads -= 1

        with patch.object(PushUploader, "bulk_index_single_batch_upload", side_effect=upload_batch):
            await connector.index_data_async(options=ConnectorOptions(upload_max_workers=2))

        assert max_active_uploads == 2

    @pytest.mark.asyncio
    async def test_index_data_async_exact_batch_size_multiple(self):
        """Test that exact batch_size multiple correctly sets is_last_page=True."""
        items = [
            {"id": f"doc-{i}", "title": f"Doc {i}", "content": f"Content {i}"} for i in range(4)
        ]
        client = DummyAsyncDataClient(items=items)
        connector = DummyAsyncConnector("test", client)
        connector.batch_size = 2

        with patch("glean.indexing.push.uploader.api_client") as mock_api_client:
            bulk_index = mock_api_client().__enter__().indexing.documents.bulk_index
            await connector.index_data_async()

            assert bulk_index.call_count == 2

            first_call = bulk_index.call_args_list[0][1]
            assert first_call["is_first_page"] is True
            assert first_call["is_last_page"] is False
            assert len(first_call["documents"]) == 2

            last_call = bulk_index.call_args_list[1][1]
            assert last_call["is_first_page"] is False
            assert last_call["is_last_page"] is True
            assert len(last_call["documents"]) == 2

    @pytest.mark.asyncio
    async def test_index_data_async_force_restart(self):
        """Test that force_restart option sets force_restart_upload on first batch."""
        client = DummyAsyncDataClient()
        connector = DummyAsyncConnector("test", client)
        connector.batch_size = 2

        with patch("glean.indexing.push.uploader.api_client") as mock_api_client:
            bulk_index = mock_api_client().__enter__().indexing.documents.bulk_index
            await connector.index_data_async(options=ConnectorOptions(force_restart=True))

            # First batch should have force_restart_upload=True
            first_call = bulk_index.call_args_list[0][1]
            assert first_call["force_restart_upload"] is True

            # Subsequent batches should have force_restart_upload=None
            second_call = bulk_index.call_args_list[1][1]
            assert second_call["force_restart_upload"] is None

    @pytest.mark.asyncio
    async def test_index_data_async_error_handling(self):
        """Test that errors during indexing are propagated."""
        client = DummyAsyncDataClient()
        connector = DummyAsyncConnector("test", client)

        with patch("glean.indexing.push.uploader.api_client") as mock_api_client:
            bulk_index = mock_api_client().__enter__().indexing.documents.bulk_index
            bulk_index.side_effect = Exception("upload failed")

            with pytest.raises(Exception, match="upload failed"):
                await connector.index_data_async()

    @pytest.mark.asyncio
    async def test_index_data_async_emits_success_lifecycle_and_metrics(self):
        connector = DummyAsyncConnector("test", DummyAsyncDataClient())
        connector.batch_size = 2
        metrics = InMemoryMetricsProvider()
        connector.observability.metrics_provider = metrics

        with (
            TestCase().assertLogs(
                "glean.indexing.observability.observability", level="INFO"
            ) as captured,
            patch("glean.indexing.push.uploader.api_client"),
        ):
            await connector.index_data_async()

        operations = [getattr(record, "operation", None) for record in captured.records]
        assert operations.count("crawl_started") == 1
        assert operations.count("crawl_completed") == 1
        assert "crawl_failed" not in operations
        summary = connector.observability.get_metrics_summary()
        assert (
            summary.items()
            >= {
                "items_fetched": 5,
                "documents_transformed": 5,
                "documents_indexed": 5,
            }.items()
        )
        assert {"data_fetch_duration", "data_transform_duration"} <= summary.keys()
        assert "data_upload_duration" not in summary
        emitted_metric_names = {metric["name"] for metric in metrics.get_metric_history()}
        assert {
            "api_request_count",
            "api_request_latency_ms",
            "connector_execution_duration_ms",
        } <= emitted_metric_names

    @pytest.mark.asyncio
    async def test_slow_async_streaming_fetch_is_not_reported_as_upload_duration(self):
        class SlowClient(DummyAsyncDataClient):
            async def get_source_data(self, **kwargs):
                for item in self.items:
                    await asyncio.sleep(0.01)
                    yield item

        connector = DummyAsyncConnector("test", SlowClient())
        metrics = InMemoryMetricsProvider()
        connector.observability.metrics_provider = metrics

        with patch("glean.indexing.push.uploader.api_client"):
            await connector.index_data_async()

        summary = connector.observability.get_metrics_summary()
        assert summary["data_fetch_duration"] >= 0.04
        assert "data_upload_duration" not in summary
        assert any(
            metric["name"] == "api_request_latency_ms"
            and metric["labels"]["endpoint"] == "documents.bulk_index"
            for metric in metrics.get_metric_history()
        )

    @pytest.mark.asyncio
    async def test_async_streaming_fetch_failure_records_partial_counts_and_duration(self):
        class FailingClient(DummyAsyncDataClient):
            async def get_source_data(self, **kwargs):
                for index, item in enumerate(self.items):
                    await asyncio.sleep(0.01)
                    yield item
                    if index == 2:
                        await asyncio.sleep(0.01)
                        raise RuntimeError("fetch failed")

        connector = DummyAsyncConnector("test", FailingClient())
        connector.batch_size = 2

        with (
            patch("glean.indexing.push.uploader.api_client"),
            pytest.raises(RuntimeError, match="fetch failed"),
        ):
            await connector.index_data_async()

        summary = connector.observability.get_metrics_summary()
        assert summary["items_fetched"] == 3
        assert summary["documents_transformed"] == 2
        assert summary["data_fetch_duration"] >= 0.035
        assert summary["data_transform_duration"] >= 0

    @pytest.mark.asyncio
    async def test_async_streaming_transform_failure_records_failed_call_duration(self):
        class FailingTransformConnector(DummyAsyncConnector):
            def __init__(self, name, data_client):
                super().__init__(name, data_client)
                self.transform_calls = 0

            def transform(self, data):
                self.transform_calls += 1
                time.sleep(0.01)
                if self.transform_calls == 2:
                    raise RuntimeError("transform failed")
                return super().transform(data)

        connector = FailingTransformConnector("test", DummyAsyncDataClient())
        connector.batch_size = 2

        with (
            patch("glean.indexing.push.uploader.api_client"),
            pytest.raises(RuntimeError, match="transform failed"),
        ):
            await connector.index_data_async()

        summary = connector.observability.get_metrics_summary()
        assert summary["items_fetched"] == 4
        assert summary["documents_transformed"] == 2
        assert summary["data_transform_duration"] >= 0.018

    @pytest.mark.asyncio
    async def test_index_data_async_emits_failure_lifecycle_and_metrics(self):
        connector = DummyAsyncConnector("test", DummyAsyncDataClient())
        metrics = InMemoryMetricsProvider()
        connector.observability.metrics_provider = metrics

        with (
            TestCase().assertLogs(
                "glean.indexing.observability.observability", level="INFO"
            ) as captured,
            patch("glean.indexing.push.uploader.api_client") as api_client,
        ):
            api_client().__enter__().indexing.documents.bulk_index.side_effect = RuntimeError(
                "upload failed"
            )
            with pytest.raises(RuntimeError, match="upload failed"):
                await connector.index_data_async()

        operations = [getattr(record, "operation", None) for record in captured.records]
        assert operations.count("crawl_started") == 1
        assert operations.count("crawl_failed") == 1
        assert "crawl_completed" not in operations
        assert connector.observability.get_metrics_summary()["indexing_errors"] == 1
        assert "connector_execution_duration_ms" in {
            metric["name"] for metric in metrics.get_metric_history()
        }

    @pytest.mark.asyncio
    async def test_disable_stale_deletion_check_on_last_page_only(self):
        """Test that disable_stale_document_deletion_check is set only on the last batch."""
        client = DummyAsyncDataClient()
        connector = DummyAsyncConnector("test", client)
        connector.batch_size = 2

        with patch("glean.indexing.push.uploader.api_client") as mock_api_client:
            bulk_index = mock_api_client().__enter__().indexing.documents.bulk_index
            await connector.index_data_async(
                options=ConnectorOptions(disable_stale_deletion_check=True)
            )

            # 5 items with batch_size=2 = 3 batches
            assert bulk_index.call_count == 3

            first_call = bulk_index.call_args_list[0][1]
            assert first_call["disable_stale_document_deletion_check"] is None

            second_call = bulk_index.call_args_list[1][1]
            assert second_call["disable_stale_document_deletion_check"] is None

            last_call = bulk_index.call_args_list[2][1]
            assert last_call["disable_stale_document_deletion_check"] is True

    @pytest.mark.asyncio
    async def test_upload_timeout_ms_passed_to_bulk_index(self):
        """Test that upload_timeout_ms is forwarded to every bulk_index call."""
        client = DummyAsyncDataClient()
        connector = DummyAsyncConnector("test", client)
        connector.batch_size = 2

        with patch("glean.indexing.push.uploader.api_client") as mock_api_client:
            bulk_index = mock_api_client().__enter__().indexing.documents.bulk_index
            await connector.index_data_async(options=ConnectorOptions(upload_timeout_ms=120_000))

            assert bulk_index.call_count == 3
            for call in bulk_index.call_args_list:
                assert call[1]["timeout_ms"] == 120_000

    @pytest.mark.asyncio
    async def test_upload_timeout_ms_defaults_to_none(self):
        """Test that timeout_ms is None when no options are provided (SDK default applies)."""
        client = DummyAsyncDataClient()
        connector = DummyAsyncConnector("test", client)

        with patch("glean.indexing.push.uploader.api_client") as mock_api_client:
            bulk_index = mock_api_client().__enter__().indexing.documents.bulk_index
            await connector.index_data_async()

            assert bulk_index.call_args[1].get("timeout_ms") is None

    @pytest.mark.asyncio
    async def test_document_batch_size_bytes_splits_oversized_batch(self):
        """Regression test: document_batch_size_bytes must split async-streamed
        documents that would otherwise fit in a single count-based batch."""
        client = DummyAsyncDataClient(
            items=[
                {"id": f"doc-{i}", "title": "x" * 300, "content": f"Content {i}"} for i in range(2)
            ]
        )
        connector = DummyAsyncConnector("test", client)
        # Count-based batch size alone would fit both documents in a single upload.
        connector.batch_size = 10

        with patch("glean.indexing.push.uploader.api_client") as mock_api_client:
            bulk_index = mock_api_client().__enter__().indexing.documents.bulk_index
            await connector.index_data_async(
                options=ConnectorOptions(document_batch_size_bytes=100)
            )

            assert bulk_index.call_count == 2

            first_call = bulk_index.call_args_list[0][1]
            assert len(first_call["documents"]) == 1
            assert first_call["is_first_page"] is True
            assert first_call["is_last_page"] is False

            last_call = bulk_index.call_args_list[1][1]
            assert len(last_call["documents"]) == 1
            assert last_call["is_first_page"] is False
            assert last_call["is_last_page"] is True

    def test_sync_fallback_get_data(self):
        """Test that sync get_data() works as fallback."""
        connector = DummyAsyncConnector("test", DummyAsyncDataClient())
        data = connector.get_data()
        assert len(data) == 5

    def test_sync_fallback_index_data(self):
        """Test that sync index_data() works as fallback."""
        connector = DummyAsyncConnector("test", DummyAsyncDataClient())
        connector.batch_size = 10

        with patch("glean.indexing.push.uploader.api_client") as mock_api_client:
            bulk_index = mock_api_client().__enter__().indexing.documents.bulk_index
            connector.index_data()
            assert bulk_index.call_count == 1

    def test_sync_fallback_emits_one_lifecycle(self):
        connector = DummyAsyncConnector("test", DummyAsyncDataClient())

        with (
            TestCase().assertLogs(
                "glean.indexing.observability.observability", level="INFO"
            ) as captured,
            patch("glean.indexing.push.uploader.api_client"),
        ):
            connector.index_data()

        operations = [getattr(record, "operation", None) for record in captured.records]
        assert operations.count("crawl_started") == 1
        assert operations.count("crawl_completed") == 1
