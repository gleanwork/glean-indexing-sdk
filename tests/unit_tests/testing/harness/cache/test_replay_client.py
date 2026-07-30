"""Tests for ReplayDataClientWrapper and its streaming siblings."""

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
from glean.indexing.testing.harness.cache.replay_client import (
    ReplayAsyncStreamingClientWrapper,
    ReplayDataClientWrapper,
    ReplayStreamingClientWrapper,
)

_ITEMS = [{"id": str(i), "val": i * 10} for i in range(4)]
_SDK_VER = "1.0.0b2"


def _write_fixture(
    tmp_path: Path,
    connector_name: str,
    client_name: str,
    items: list,
) -> Path:
    """Helper: write an NDJSON fixture without going through the recording wrapper."""
    fixture_dir = tmp_path / connector_name / "integration" / client_name
    fixture_dir.mkdir(parents=True, exist_ok=True)
    data_path = fixture_dir / "data.ndjson"
    data_path.write_text("\n".join(json.dumps(item) for item in items))
    return data_path


# ---------------------------------------------------------------------------
# ReplayDataClientWrapper
# ---------------------------------------------------------------------------


class TestReplayDataClientWrapper:
    def test_replays_items(self, tmp_path: Path):
        _write_fixture(tmp_path, "conn", "data_client", _ITEMS)
        wrapper = ReplayDataClientWrapper(
            cache_dir=tmp_path, connector_name="conn", client_name="data_client"
        )
        result = list(wrapper.get_source_data())
        assert result == _ITEMS

    def test_record_then_replay(self, tmp_path: Path):
        """Full round-trip: record via RecordingDataClientWrapper, replay with Replay."""

        class _Inner(BaseDataClient[dict]):
            def get_source_data(self, **kwargs: Any) -> Sequence[dict]:
                return list(_ITEMS)

        recorder = RecordingDataClientWrapper(
            inner=_Inner(),
            cache_dir=tmp_path,
            connector_name="conn",
            client_name="data_client",
            sdk_version=_SDK_VER,
        )
        recorder.get_source_data()  # write fixture

        replayer = ReplayDataClientWrapper(
            cache_dir=tmp_path, connector_name="conn", client_name="data_client"
        )
        assert list(replayer.get_source_data()) == _ITEMS

    def test_missing_cache_raises(self, tmp_path: Path):
        wrapper = ReplayDataClientWrapper(
            cache_dir=tmp_path, connector_name="conn", client_name="missing"
        )
        with pytest.raises(FileNotFoundError, match="missing"):
            wrapper.get_source_data()

    def test_empty_cache_raises(self, tmp_path: Path):
        fixture_dir = tmp_path / "conn" / "integration" / "empty_client"
        fixture_dir.mkdir(parents=True)
        (fixture_dir / "data.ndjson").write_text("")

        wrapper = ReplayDataClientWrapper(
            cache_dir=tmp_path, connector_name="conn", client_name="empty_client"
        )
        with pytest.raises(ValueError, match="empty"):
            wrapper.get_source_data()


# ---------------------------------------------------------------------------
# ReplayStreamingClientWrapper
# ---------------------------------------------------------------------------


class TestReplayStreamingClientWrapper:
    def test_yields_items(self, tmp_path: Path):
        _write_fixture(tmp_path, "conn", "stream", _ITEMS)
        wrapper = ReplayStreamingClientWrapper(
            cache_dir=tmp_path, connector_name="conn", client_name="stream"
        )
        assert list(wrapper.get_source_data()) == _ITEMS

    def test_record_then_replay(self, tmp_path: Path):
        class _Inner(BaseStreamingDataClient[dict]):
            def get_source_data(self, **kwargs: Any) -> Generator[dict, None, None]:
                yield from _ITEMS

        recorder = RecordingStreamingClientWrapper(
            inner=_Inner(),
            cache_dir=tmp_path,
            connector_name="conn",
            client_name="stream",
            sdk_version=_SDK_VER,
        )
        list(recorder.get_source_data())

        replayer = ReplayStreamingClientWrapper(
            cache_dir=tmp_path, connector_name="conn", client_name="stream"
        )
        assert list(replayer.get_source_data()) == _ITEMS

    def test_missing_cache_raises(self, tmp_path: Path):
        wrapper = ReplayStreamingClientWrapper(
            cache_dir=tmp_path, connector_name="conn", client_name="nope"
        )
        with pytest.raises(FileNotFoundError):
            list(wrapper.get_source_data())


# ---------------------------------------------------------------------------
# ReplayAsyncStreamingClientWrapper
# ---------------------------------------------------------------------------


class TestReplayAsyncStreamingClientWrapper:
    @pytest.mark.asyncio
    async def test_yields_items(self, tmp_path: Path):
        _write_fixture(tmp_path, "conn", "async_cl", _ITEMS)
        wrapper = ReplayAsyncStreamingClientWrapper(
            cache_dir=tmp_path, connector_name="conn", client_name="async_cl"
        )
        result = []
        async for item in wrapper.get_source_data():
            result.append(item)
        assert result == _ITEMS

    @pytest.mark.asyncio
    async def test_record_then_replay(self, tmp_path: Path):
        class _Inner(BaseAsyncStreamingDataClient[dict]):
            async def get_source_data(self, **kwargs: Any) -> AsyncGenerator[dict, None]:
                for item in _ITEMS:
                    yield item

        recorder = RecordingAsyncStreamingClientWrapper(
            inner=_Inner(),
            cache_dir=tmp_path,
            connector_name="conn",
            client_name="async_cl",
            sdk_version=_SDK_VER,
        )
        async for _ in recorder.get_source_data():
            pass

        replayer = ReplayAsyncStreamingClientWrapper(
            cache_dir=tmp_path, connector_name="conn", client_name="async_cl"
        )
        result = []
        async for item in replayer.get_source_data():
            result.append(item)
        assert result == _ITEMS

    @pytest.mark.asyncio
    async def test_missing_cache_raises(self, tmp_path: Path):
        wrapper = ReplayAsyncStreamingClientWrapper(
            cache_dir=tmp_path, connector_name="conn", client_name="gone"
        )
        with pytest.raises(FileNotFoundError):
            async for _ in wrapper.get_source_data():
                pass
