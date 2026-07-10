"""Tests for RecordingDataClientWrapper and its streaming siblings."""

import json
from pathlib import Path
from typing import Any, AsyncGenerator, Generator, Sequence

import pytest

from glean.indexing.connectors.base_async_streaming_data_client import BaseAsyncStreamingDataClient
from glean.indexing.connectors.base_data_client import BaseDataClient
from glean.indexing.connectors.base_streaming_data_client import BaseStreamingDataClient
from glean.indexing.testing.harness.cache.recording_client import (
    RecordingAsyncStreamingClientWrapper,
    RecordingDataClientWrapper,
    RecordingStreamingClientWrapper,
)

_ITEMS = [{"id": str(i), "title": f"Item {i}"} for i in range(5)]
_SDK_VER = "1.0.0b2"


# ---------------------------------------------------------------------------
# Minimal inner clients for testing
# ---------------------------------------------------------------------------


class _FakeDataClient(BaseDataClient[dict]):
    def __init__(self, items: list) -> None:
        self._items = items

    def get_source_data(self, **kwargs: Any) -> Sequence[dict]:
        return list(self._items)


class _FakeStreamingClient(BaseStreamingDataClient[dict]):
    def __init__(self, items: list) -> None:
        self._items = items

    def get_source_data(self, **kwargs: Any) -> Generator[dict, None, None]:
        yield from self._items


class _FakeAsyncStreamingClient(BaseAsyncStreamingDataClient[dict]):
    def __init__(self, items: list) -> None:
        self._items = items

    async def get_source_data(self, **kwargs: Any) -> AsyncGenerator[dict, None]:
        for item in self._items:
            yield item


# ---------------------------------------------------------------------------
# RecordingDataClientWrapper
# ---------------------------------------------------------------------------


class TestRecordingDataClientWrapper:
    def test_returns_items(self, tmp_path: Path):
        wrapper = RecordingDataClientWrapper(
            inner=_FakeDataClient(_ITEMS),
            cache_dir=tmp_path,
            connector_name="my_conn",
            client_name="data_client",
            sdk_version=_SDK_VER,
        )
        result = wrapper.get_source_data()
        assert list(result) == _ITEMS

    def test_writes_ndjson(self, tmp_path: Path):
        wrapper = RecordingDataClientWrapper(
            inner=_FakeDataClient(_ITEMS),
            cache_dir=tmp_path,
            connector_name="my_conn",
            client_name="data_client",
            sdk_version=_SDK_VER,
        )
        wrapper.get_source_data()

        data_path = tmp_path / "my_conn" / "integration" / "data_client" / "data.ndjson"
        assert data_path.exists()
        lines = data_path.read_text().splitlines()
        assert len(lines) == 5
        assert json.loads(lines[0]) == {"id": "0", "title": "Item 0"}

    def test_writes_manifest(self, tmp_path: Path):
        wrapper = RecordingDataClientWrapper(
            inner=_FakeDataClient(_ITEMS),
            cache_dir=tmp_path,
            connector_name="my_conn",
            client_name="data_client",
            sdk_version=_SDK_VER,
        )
        wrapper.get_source_data()

        manifest_path = tmp_path / "my_conn" / "integration" / "data_client" / "manifest.json"
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text())
        assert data["item_count"] == 5
        assert data["sdk_version"] == _SDK_VER
        assert data["connector"] == "my_conn"
        assert data["client"] == "data_client"

    def test_max_items_respected(self, tmp_path: Path):
        wrapper = RecordingDataClientWrapper(
            inner=_FakeDataClient(_ITEMS),
            cache_dir=tmp_path,
            connector_name="my_conn",
            client_name="data_client",
            max_items=3,
            sdk_version=_SDK_VER,
        )
        result = list(wrapper.get_source_data())
        assert len(result) == 3
        assert result == _ITEMS[:3]

        data_path = tmp_path / "my_conn" / "integration" / "data_client" / "data.ndjson"
        assert len(data_path.read_text().splitlines()) == 3

    def test_max_items_none_records_all(self, tmp_path: Path):
        wrapper = RecordingDataClientWrapper(
            inner=_FakeDataClient(_ITEMS),
            cache_dir=tmp_path,
            connector_name="my_conn",
            client_name="data_client",
            max_items=None,
            sdk_version=_SDK_VER,
        )
        result = list(wrapper.get_source_data())
        assert len(result) == 5


# ---------------------------------------------------------------------------
# RecordingStreamingClientWrapper
# ---------------------------------------------------------------------------


class TestRecordingStreamingClientWrapper:
    def test_yields_items(self, tmp_path: Path):
        wrapper = RecordingStreamingClientWrapper(
            inner=_FakeStreamingClient(_ITEMS),
            cache_dir=tmp_path,
            connector_name="conn",
            client_name="stream_client",
            sdk_version=_SDK_VER,
        )
        result = list(wrapper.get_source_data())
        assert result == _ITEMS

    def test_writes_ndjson(self, tmp_path: Path):
        wrapper = RecordingStreamingClientWrapper(
            inner=_FakeStreamingClient(_ITEMS),
            cache_dir=tmp_path,
            connector_name="conn",
            client_name="stream_client",
            sdk_version=_SDK_VER,
        )
        list(wrapper.get_source_data())

        data_path = tmp_path / "conn" / "integration" / "stream_client" / "data.ndjson"
        assert data_path.exists()
        assert len(data_path.read_text().splitlines()) == 5

    def test_max_items_respected(self, tmp_path: Path):
        wrapper = RecordingStreamingClientWrapper(
            inner=_FakeStreamingClient(_ITEMS),
            cache_dir=tmp_path,
            connector_name="conn",
            client_name="stream_client",
            max_items=2,
            sdk_version=_SDK_VER,
        )
        result = list(wrapper.get_source_data())
        assert len(result) == 2


# ---------------------------------------------------------------------------
# RecordingAsyncStreamingClientWrapper
# ---------------------------------------------------------------------------


class TestRecordingAsyncStreamingClientWrapper:
    @pytest.mark.asyncio
    async def test_yields_items(self, tmp_path: Path):
        wrapper = RecordingAsyncStreamingClientWrapper(
            inner=_FakeAsyncStreamingClient(_ITEMS),
            cache_dir=tmp_path,
            connector_name="conn",
            client_name="async_client",
            sdk_version=_SDK_VER,
        )
        result = []
        async for item in wrapper.get_source_data():
            result.append(item)
        assert result == _ITEMS

    @pytest.mark.asyncio
    async def test_writes_ndjson(self, tmp_path: Path):
        wrapper = RecordingAsyncStreamingClientWrapper(
            inner=_FakeAsyncStreamingClient(_ITEMS),
            cache_dir=tmp_path,
            connector_name="conn",
            client_name="async_client",
            sdk_version=_SDK_VER,
        )
        async for _ in wrapper.get_source_data():
            pass

        data_path = tmp_path / "conn" / "integration" / "async_client" / "data.ndjson"
        assert data_path.exists()
        assert len(data_path.read_text().splitlines()) == 5

    @pytest.mark.asyncio
    async def test_max_items_respected(self, tmp_path: Path):
        wrapper = RecordingAsyncStreamingClientWrapper(
            inner=_FakeAsyncStreamingClient(_ITEMS),
            cache_dir=tmp_path,
            connector_name="conn",
            client_name="async_client",
            max_items=2,
            sdk_version=_SDK_VER,
        )
        result = []
        async for item in wrapper.get_source_data():
            result.append(item)
        assert len(result) == 2
