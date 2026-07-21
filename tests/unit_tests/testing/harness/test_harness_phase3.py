"""Tests for TestHarness Phase 3 — end-to-end (real source, real Glean).

Unit tests here validate the method interface and max_items wiring without
making actual network calls.  Live end-to-end runs are manual — point
``GLEAN_SERVER_URL`` at a test instance and set ``GLEAN_INDEXING_API_TOKEN``
before calling ``harness.run_end_to_end()``.
"""

from pathlib import Path
from typing import Any, AsyncGenerator, Sequence
from unittest.mock import AsyncMock, patch

import pytest

from glean.indexing.connectors.base_async_streaming_data_client import BaseAsyncStreamingDataClient
from glean.indexing.connectors.base_data_client import BaseDataClient
from glean.indexing.models import IndexingMode
from glean.indexing.testing import StaticDataClient, mock_glean_client
from glean.indexing.testing.harness import TestConfig, TestHarness
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
    def test_calls_index_data(self, tmp_path: Path):
        """run_end_to_end should call connector.index_data() (mocked)."""
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(_DOCS))
        config = TestConfig(cache_dir=str(tmp_path))
        harness = TestHarness(connector=connector, config=config)

        with patch.object(connector, "index_data") as mock_index:
            harness.run_end_to_end()
            mock_index.assert_called_once_with(mode=IndexingMode.FULL, options=None)

    def test_mode_forwarded(self, tmp_path: Path):
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(_DOCS))
        harness = TestHarness(connector=connector, config=TestConfig(cache_dir=str(tmp_path)))

        with patch.object(connector, "index_data") as mock_index:
            harness.run_end_to_end(mode=IndexingMode.INCREMENTAL)
            mock_index.assert_called_once_with(mode=IndexingMode.INCREMENTAL, options=None)

    @patch("glean.indexing.testing.harness.harness.wait_for_documents_to_index")
    def test_waits_for_uploaded_documents(self, wait_for_documents, tmp_path: Path):
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(_DOCS))
        config = TestConfig(
            cache_dir=str(tmp_path),
            initial_index_wait_seconds=35,
            index_poll_interval_seconds=10,
            index_wait_timeout_seconds=120,
        )
        harness = TestHarness(connector=connector, config=config)

        with mock_glean_client():
            harness.run_end_to_end()

        wait_for_documents.assert_called_once()
        args, kwargs = wait_for_documents.call_args
        assert args[0] == "ds"
        assert len(args[1]) == len(_DOCS)
        assert kwargs == {
            "initial_wait_seconds": 35,
            "poll_interval_seconds": 10,
            "timeout_seconds": 120,
        }

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
                harness.run_end_to_end()

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
                harness.run_end_to_end()

        assert connector.data_client is real_client


class TestRunEndToEndAsync:
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
            await harness.run_end_to_end_async()
            mock_async.assert_awaited_once_with(mode=IndexingMode.FULL, options=None)

    @pytest.mark.asyncio
    async def test_sync_connector_calls_index_data(self, tmp_path: Path):
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(_DOCS))
        config = TestConfig(cache_dir=str(tmp_path))
        harness = TestHarness(connector=connector, config=config)

        with patch.object(connector, "index_data") as mock_index:
            await harness.run_end_to_end_async()
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
                await harness.run_end_to_end_async()

        assert connector.async_data_client is real_client
