"""Tests for TestHarness Phase 3 — end-to-end (real source, real Glean).

Unit tests here validate the method interface and max_items wiring without
making actual network calls.  Live end-to-end runs are manual — point
``GLEAN_SERVER_URL`` at a test instance and set ``GLEAN_INDEXING_API_TOKEN``
before calling ``harness.run_end_to_end(confirm=True, allow_destructive=True)``.
"""

from pathlib import Path
from typing import Any, AsyncGenerator, Sequence
from unittest.mock import AsyncMock, patch

import pytest

from glean.indexing.connectors.base_async_streaming_data_client import BaseAsyncStreamingDataClient
from glean.indexing.connectors.base_data_client import BaseDataClient
from glean.indexing.exceptions import (
    LiveEndToEndNotConfirmedError,
    UnsafeLiveEndToEndRunError,
)
from glean.indexing.models import IndexingMode
from glean.indexing.testing import StaticDataClient, mock_glean_client
from glean.indexing.testing.harness import IndexingWaitResult, TestConfig, TestHarness
from glean.indexing.testing.harness.config import ClientConfig
from tests.unit_tests.testing._fakes import AsyncStreamingFake, DatasourceFake

_DOCS = [{"id": str(i), "title": f"Doc {i}"} for i in range(3)]


class _CountingDataClient(BaseDataClient[dict]):
    def __init__(self, items: list) -> None:
        self._items = items
        self.call_count = 0

    def get_source_data(self, **kwargs: Any) -> Sequence[dict]:
        self.call_count += 1
        return list(self._items)


class _CountingAsyncClient(BaseAsyncStreamingDataClient[dict]):
    def __init__(self, items: list) -> None:
        self._items = items
        self.call_count = 0

    async def get_source_data(self, **kwargs: Any) -> AsyncGenerator[dict, None]:
        self.call_count += 1
        for item in self._items:
            yield item


# ---------------------------------------------------------------------------
# Unit tests — interface validation (no real Glean calls)
# ---------------------------------------------------------------------------


class TestRunEndToEnd:
    def test_refuses_to_run_without_confirmation(self, tmp_path: Path, monkeypatch):
        """The only guard against a misconfigured GLEAN_SERVER_URL is refusing by default."""
        monkeypatch.delenv("GLEAN_SERVER_URL", raising=False)
        monkeypatch.delenv("GLEAN_INSTANCE", raising=False)
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(_DOCS))
        harness = TestHarness(connector=connector, config=TestConfig(cache_dir=str(tmp_path)))

        with patch.object(connector, "index_data") as mock_index:
            with pytest.raises(LiveEndToEndNotConfirmedError):
                harness.run_end_to_end()
            mock_index.assert_not_called()

    def test_confirmation_does_not_authorize_destructive_replacement(self, tmp_path: Path):
        docs = [{"id": str(i), "title": f"Doc {i}"} for i in range(20)]
        real_client = _CountingDataClient(docs)
        connector = DatasourceFake(name="ds", data_client=real_client)
        harness = TestHarness(
            connector=connector,
            config=TestConfig(
                cache_dir=str(tmp_path),
                use_cache=False,
                clients={"data_client": ClientConfig(max_items=2)},
            ),
            clients={"data_client": real_client},
        )

        with mock_glean_client() as glean_client:
            with pytest.raises(UnsafeLiveEndToEndRunError):
                harness.run_end_to_end(confirm=True)

        assert real_client.call_count == 0
        glean_client.indexing.documents.bulk_index.assert_not_called()

    def test_confirmation_error_names_the_resolved_target(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("GLEAN_SERVER_URL", "https://prod-be.glean.com")
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(_DOCS))
        harness = TestHarness(connector=connector, config=TestConfig(cache_dir=str(tmp_path)))

        with pytest.raises(LiveEndToEndNotConfirmedError, match="prod-be.glean.com"):
            harness.run_end_to_end()

    def test_calls_index_data(self, tmp_path: Path):
        """run_end_to_end should call connector.index_data() (mocked)."""
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(_DOCS))
        config = TestConfig(cache_dir=str(tmp_path))
        harness = TestHarness(connector=connector, config=config)

        with patch.object(connector, "index_data") as mock_index:
            harness.run_end_to_end(confirm=True, allow_destructive=True)
            mock_index.assert_called_once_with(mode=IndexingMode.FULL, options=None)

    def test_mode_forwarded(self, tmp_path: Path):
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(_DOCS))
        harness = TestHarness(connector=connector, config=TestConfig(cache_dir=str(tmp_path)))

        with patch.object(connector, "index_data") as mock_index:
            harness.run_end_to_end(
                mode=IndexingMode.INCREMENTAL,
                confirm=True,
                allow_destructive=True,
            )
            mock_index.assert_called_once_with(mode=IndexingMode.INCREMENTAL, options=None)

    @patch("glean.indexing.testing.harness.harness.wait_for_documents_to_index")
    def test_waits_for_uploaded_documents(self, wait_for_documents, tmp_path: Path):
        wait_for_documents.return_value = IndexingWaitResult.PENDING
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(_DOCS))
        config = TestConfig(cache_dir=str(tmp_path))
        harness = TestHarness(connector=connector, config=config)

        with mock_glean_client():
            result = harness.run_end_to_end(confirm=True, allow_destructive=True)

        assert result is IndexingWaitResult.PENDING
        wait_for_documents.assert_called_once()
        args, kwargs = wait_for_documents.call_args
        assert args[0] == "ds"
        assert len(args[1]) == len(_DOCS)
        assert kwargs == {}

    @patch("glean.indexing.testing.harness.harness.wait_for_documents_to_index")
    @patch("glean.indexing.testing.harness.harness.logger")
    def test_logs_cleanup_command_for_uploaded_documents(
        self, mock_logger, wait_for_documents, tmp_path: Path
    ):
        # Not caplog: the project's pytest config runs with `-p no:logging`,
        # which disables the fixture caplog depends on.
        wait_for_documents.return_value = IndexingWaitResult.PENDING
        typed_docs = [{**doc, "object_type": "Article"} for doc in _DOCS]
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(typed_docs))
        config = TestConfig(cache_dir=str(tmp_path))
        harness = TestHarness(connector=connector, config=config)

        with mock_glean_client():
            harness.run_end_to_end(confirm=True, allow_destructive=True)

        cleanup_calls = [
            call.args
            for call in mock_logger.warning.call_args_list
            if "document delete" in call.args[0]
        ]
        assert len(cleanup_calls) == 1
        message = cleanup_calls[0][0] % cleanup_calls[0][1:]
        assert "glean-idx document delete --datasource ds" in message
        for doc in typed_docs:
            assert f"--document Article {doc['id']}" in message

    def test_max_items_applied_to_client(self, tmp_path: Path):
        """Clients should be patched with recording wrappers that enforce max_items."""
        real_client = _CountingDataClient(_DOCS)
        connector = DatasourceFake(name="ds", data_client=real_client)
        config = TestConfig(
            cache_dir=str(tmp_path),
            use_cache=False,
            clients={"data_client": ClientConfig(max_items=2)},
        )
        harness = TestHarness(
            connector=connector,
            config=config,
            clients={"data_client": real_client},
        )

        class _PatchingConfirmed(Exception):
            pass

        def _verify_wrapping_then_raise(mode, options):
            # If the client is the original it means patching didn't happen.
            assert connector.data_client is not real_client, "client should be wrapped"
            raise _PatchingConfirmed("wrapping confirmed — abort before real Glean call")

        with patch.object(connector, "index_data", side_effect=_verify_wrapping_then_raise):
            with pytest.raises(_PatchingConfirmed):
                harness.run_end_to_end(confirm=True, allow_destructive=True)

        # Client must be restored after run
        assert connector.data_client is real_client

    def test_client_restored_after_exception(self, tmp_path: Path):
        """Even if index_data raises, the connector attribute should be restored."""
        real_client = _CountingDataClient(_DOCS)
        connector = DatasourceFake(name="ds", data_client=real_client)
        config = TestConfig(cache_dir=str(tmp_path), use_cache=False)
        harness = TestHarness(
            connector=connector,
            config=config,
            clients={"data_client": real_client},
        )

        with patch.object(connector, "index_data", side_effect=RuntimeError("no creds")):
            with pytest.raises(RuntimeError, match="no creds"):
                harness.run_end_to_end(confirm=True, allow_destructive=True)

        assert connector.data_client is real_client


class TestRunEndToEndAsync:
    @pytest.mark.asyncio
    async def test_refuses_to_run_without_confirmation(self, tmp_path: Path):
        from glean.indexing.testing import StaticAsyncStreamingDataClient

        connector = AsyncStreamingFake(
            name="as",
            async_data_client=StaticAsyncStreamingDataClient(_DOCS),
        )
        harness = TestHarness(connector=connector, config=TestConfig(cache_dir=str(tmp_path)))

        with patch.object(connector, "index_data_async", new_callable=AsyncMock) as mock_async:
            with pytest.raises(LiveEndToEndNotConfirmedError):
                await harness.run_end_to_end_async()
            mock_async.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_confirmation_does_not_authorize_destructive_async_replacement(
        self, tmp_path: Path
    ):
        from glean.indexing.testing import StaticAsyncStreamingDataClient

        client = StaticAsyncStreamingDataClient(_DOCS)
        connector = AsyncStreamingFake(name="as", async_data_client=client)
        harness = TestHarness(
            connector=connector,
            config=TestConfig(cache_dir=str(tmp_path)),
            clients={"async_data_client": client},
        )

        with patch.object(connector, "index_data_async", new_callable=AsyncMock) as mock_async:
            with pytest.raises(UnsafeLiveEndToEndRunError):
                await harness.run_end_to_end_async(confirm=True)
            mock_async.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_async_connector_calls_index_data_async(self, tmp_path: Path):
        from glean.indexing.testing import StaticAsyncStreamingDataClient

        connector = AsyncStreamingFake(
            name="as",
            async_data_client=StaticAsyncStreamingDataClient(_DOCS),
        )
        config = TestConfig(cache_dir=str(tmp_path))
        harness = TestHarness(connector=connector, config=config)

        with patch.object(connector, "index_data_async", new_callable=AsyncMock) as mock_async:
            await harness.run_end_to_end_async(confirm=True, allow_destructive=True)
            mock_async.assert_awaited_once_with(mode=IndexingMode.FULL, options=None)

    @pytest.mark.asyncio
    async def test_sync_connector_calls_index_data(self, tmp_path: Path):
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(_DOCS))
        config = TestConfig(cache_dir=str(tmp_path))
        harness = TestHarness(connector=connector, config=config)

        with patch.object(connector, "index_data") as mock_index:
            await harness.run_end_to_end_async(confirm=True, allow_destructive=True)
            mock_index.assert_called_once_with(mode=IndexingMode.FULL, options=None)

    @pytest.mark.asyncio
    async def test_client_restored_after_exception(self, tmp_path: Path):
        real_client = _CountingAsyncClient(_DOCS)
        connector = AsyncStreamingFake(name="as", async_data_client=real_client)
        config = TestConfig(cache_dir=str(tmp_path), use_cache=False)
        harness = TestHarness(
            connector=connector,
            config=config,
            clients={"async_data_client": real_client},
        )

        with patch.object(connector, "index_data_async", side_effect=RuntimeError("no creds")):
            with pytest.raises(RuntimeError, match="no creds"):
                await harness.run_end_to_end_async(confirm=True, allow_destructive=True)

        assert connector.async_data_client is real_client
