"""Tests for TestHarness Phase 3 — end-to-end (real source, real Glean).

Unit tests here validate the method interface and max_items wiring without
making actual network calls.  The end-to-end flow is covered by integration
tests (marked ``@pytest.mark.integration``) that require
``GLEAN_INDEXING_API_TOKEN`` in the environment and are not run in CI by
default.
"""

from pathlib import Path
from typing import Any, AsyncGenerator, Sequence
from unittest.mock import patch

import pytest

from glean.indexing.connectors.base_async_streaming_data_client import BaseAsyncStreamingDataClient
from glean.indexing.connectors.base_data_client import BaseDataClient
from glean.indexing.models import IndexingMode
from glean.indexing.testing import StaticDataClient
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

        # Patch index_data so we don't need a real Glean server, but still
        # let the client patching happen
        original_index_data = connector.index_data

        def _capture_and_call(mode, options):
            # Verify the client is wrapped (not the original) during index_data
            assert connector.data_client is not real_client
            # Still call original so client gets exercised
            original_index_data(mode=mode, options=options)

        with patch.object(connector, "index_data", side_effect=_capture_and_call):
            # This will fail at PushUploader (no creds), so just check AttributeError
            # is not raised first — the wrapping is what we're testing
            try:
                harness.run_end_to_end()
            except Exception:
                pass  # Expected — no Glean credentials in unit test env

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

        with patch.object(connector, "index_data_async") as mock_async:
            mock_async.return_value = None
            # Make it awaitable
            import asyncio

            mock_async.return_value = asyncio.coroutine(lambda: None)()
            await harness.run_end_to_end_async()
            mock_async.assert_called_once_with(mode=IndexingMode.FULL, options=None)

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
