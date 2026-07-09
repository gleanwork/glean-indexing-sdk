"""Tests for TestHarness Phase 2 — integration test (real source, mock Glean, cache)."""

import json
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Any, AsyncGenerator, Generator, Sequence

import pytest

from glean.indexing.connectors.base_async_streaming_data_client import BaseAsyncStreamingDataClient
from glean.indexing.connectors.base_data_client import BaseDataClient
from glean.indexing.connectors.base_streaming_data_client import BaseStreamingDataClient
from glean.indexing.testing import StaticDataClient
from glean.indexing.testing.harness import TestConfig, TestHarness
from glean.indexing.testing.harness.config import ClientConfig
from tests.unit_tests.testing._fakes import AsyncStreamingFake, DatasourceFake, StreamingFake

_DOCS = [{"id": str(i), "title": f"Doc {i}"} for i in range(3)]
try:
    _SDK_VER = _pkg_version("glean-indexing-sdk")
except Exception:
    _SDK_VER = "unknown"


def _fixture_data_path(cache_dir: Path, connector_name: str, client_name: str) -> Path:
    return cache_dir / connector_name / "integration" / client_name / "data.ndjson"


def _fixture_manifest_path(cache_dir: Path, connector_name: str, client_name: str) -> Path:
    return cache_dir / connector_name / "integration" / client_name / "manifest.json"


# ---------------------------------------------------------------------------
# Helpers: counting data clients
# ---------------------------------------------------------------------------


class _CountingDataClient(BaseDataClient[dict]):
    """Tracks how many times get_source_data was called."""

    def __init__(self, items: list) -> None:
        self._items = items
        self.call_count = 0

    def get_source_data(self, **kwargs: Any) -> Sequence[dict]:
        self.call_count += 1
        return list(self._items)


class _CountingStreamingClient(BaseStreamingDataClient[dict]):
    def __init__(self, items: list) -> None:
        self._items = items
        self.call_count = 0

    def get_source_data(self, **kwargs: Any) -> Generator[dict, None, None]:
        self.call_count += 1
        yield from self._items


class _CountingAsyncStreamingClient(BaseAsyncStreamingDataClient[dict]):
    def __init__(self, items: list) -> None:
        self._items = items
        self.call_count = 0

    async def get_source_data(self, **kwargs: Any) -> AsyncGenerator[dict, None]:
        self.call_count += 1
        for item in self._items:
            yield item


# ---------------------------------------------------------------------------
# Phase 2 core behaviour
# ---------------------------------------------------------------------------


class TestRunIntegrationTestCacheMiss:
    def test_first_run_records_fixture(self, tmp_path: Path):
        real_client = _CountingDataClient(_DOCS)
        connector = DatasourceFake(name="ds", data_client=real_client)
        config = TestConfig(cache_dir=str(tmp_path), use_cache=True, refresh_cache=False)

        harness = TestHarness(
            connector=connector, config=config, clients={"data_client": real_client}
        )
        result = harness.run_integration_test()

        assert real_client.call_count == 1
        result.assert_documents_posted(count=3)

        data_path = _fixture_data_path(tmp_path, "ds", "data_client")
        assert data_path.exists()
        lines = data_path.read_text().splitlines()
        assert len(lines) == 3

    def test_fixture_restored_after_run(self, tmp_path: Path):
        """Connector's data_client attribute must be restored after patching."""
        real_client = _CountingDataClient(_DOCS)
        connector = DatasourceFake(name="ds", data_client=real_client)
        config = TestConfig(cache_dir=str(tmp_path))

        harness = TestHarness(
            connector=connector, config=config, clients={"data_client": real_client}
        )
        harness.run_integration_test()

        # After the run, the connector attribute should be restored to the original
        assert connector.data_client is real_client

    def test_streaming_connector_records(self, tmp_path: Path):
        real_client = _CountingStreamingClient(_DOCS)
        connector = StreamingFake(name="ss", data_client=real_client)
        config = TestConfig(cache_dir=str(tmp_path))

        harness = TestHarness(
            connector=connector, config=config, clients={"data_client": real_client}
        )
        result = harness.run_integration_test()

        assert real_client.call_count == 1
        result.assert_documents_posted(count=3)


class TestRunIntegrationTestCacheHit:
    def _seed_fixture(self, cache_dir: Path, connector_name: str, client_name: str, items: list):
        """Write a fixture with a matching SDK version manifest."""
        from glean.indexing.testing.harness.cache.manifest import CacheManifest

        fixture_dir = cache_dir / connector_name / "integration" / client_name
        fixture_dir.mkdir(parents=True, exist_ok=True)
        (fixture_dir / "data.ndjson").write_text("\n".join(json.dumps(i) for i in items))
        m = CacheManifest.create(
            connector=connector_name,
            client=client_name,
            sdk_version=_SDK_VER,
            item_count=len(items),
        )
        m.save(fixture_dir / "manifest.json")

    def test_second_run_replays(self, tmp_path: Path):
        real_client = _CountingDataClient(_DOCS)
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(_DOCS))
        config = TestConfig(cache_dir=str(tmp_path), use_cache=True)

        # Seed a valid fixture
        self._seed_fixture(tmp_path, "ds", "data_client", _DOCS)

        harness = TestHarness(
            connector=connector, config=config, clients={"data_client": real_client}
        )
        harness.run_integration_test()

        # Real client must NOT have been called — we replayed from cache
        assert real_client.call_count == 0

    def test_refresh_cache_forces_rerecord(self, tmp_path: Path):
        real_client = _CountingDataClient(_DOCS)
        connector = DatasourceFake(name="ds", data_client=real_client)
        config = TestConfig(cache_dir=str(tmp_path), use_cache=True, refresh_cache=True)

        # Seed a valid fixture — should be ignored because refresh_cache=True
        self._seed_fixture(tmp_path, "ds", "data_client", _DOCS)

        harness = TestHarness(
            connector=connector, config=config, clients={"data_client": real_client}
        )
        harness.run_integration_test()

        assert real_client.call_count == 1

    def test_stale_manifest_forces_rerecord(self, tmp_path: Path):
        """A cached fixture with a different SDK version should cause re-recording."""
        real_client = _CountingDataClient(_DOCS)
        connector = DatasourceFake(name="ds", data_client=real_client)
        config = TestConfig(cache_dir=str(tmp_path), use_cache=True)

        # Seed a fixture with an old SDK version
        from glean.indexing.testing.harness.cache.manifest import CacheManifest

        fixture_dir = tmp_path / "ds" / "integration" / "data_client"
        fixture_dir.mkdir(parents=True)
        (fixture_dir / "data.ndjson").write_text("\n".join(json.dumps(i) for i in _DOCS))
        m = CacheManifest.create(
            connector="ds",
            client="data_client",
            sdk_version="0.0.1",  # deliberately old
            item_count=len(_DOCS),
        )
        m.save(fixture_dir / "manifest.json")

        harness = TestHarness(
            connector=connector, config=config, clients={"data_client": real_client}
        )
        harness.run_integration_test()

        assert real_client.call_count == 1


class TestRunIntegrationTestMaxItems:
    def test_max_items_limits_recorded_items(self, tmp_path: Path):
        real_client = _CountingDataClient(_DOCS)  # 3 items
        connector = DatasourceFake(name="ds", data_client=real_client)
        config = TestConfig(
            cache_dir=str(tmp_path),
            clients={"data_client": ClientConfig(max_items=2)},
        )

        harness = TestHarness(
            connector=connector, config=config, clients={"data_client": real_client}
        )
        result = harness.run_integration_test()

        # Only 2 items should have been recorded and transformed
        result.assert_documents_posted(count=2)

        data_path = _fixture_data_path(tmp_path, "ds", "data_client")
        assert len(data_path.read_text().splitlines()) == 2


class TestRunIntegrationTestErrors:
    def test_unknown_client_attr_raises(self, tmp_path: Path):
        real_client = _CountingDataClient(_DOCS)
        connector = DatasourceFake(name="ds", data_client=real_client)
        config = TestConfig(cache_dir=str(tmp_path))

        harness = TestHarness(
            connector=connector,
            config=config,
            clients={"nonexistent_attr": real_client},
        )
        with pytest.raises(AttributeError, match="nonexistent_attr"):
            harness.run_integration_test()


class TestRunIntegrationTestAsync:
    @pytest.mark.asyncio
    async def test_async_streaming_records_and_posts(self, tmp_path: Path):
        real_client = _CountingAsyncStreamingClient(_DOCS)
        connector = AsyncStreamingFake(name="as", async_data_client=real_client)
        config = TestConfig(cache_dir=str(tmp_path))

        harness = TestHarness(
            connector=connector, config=config, clients={"async_data_client": real_client}
        )
        result = await harness.run_integration_test_async()

        assert real_client.call_count == 1
        result.assert_documents_posted(count=3)

    @pytest.mark.asyncio
    async def test_async_client_attr_restored(self, tmp_path: Path):
        real_client = _CountingAsyncStreamingClient(_DOCS)
        connector = AsyncStreamingFake(name="as", async_data_client=real_client)
        config = TestConfig(cache_dir=str(tmp_path))

        harness = TestHarness(
            connector=connector, config=config, clients={"async_data_client": real_client}
        )
        await harness.run_integration_test_async()

        assert connector.async_data_client is real_client
