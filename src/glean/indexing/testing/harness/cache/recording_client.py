"""Data-client wrappers that record yielded items to NDJSON on disk.

Each wrapper class mirrors one of the three ``Base*DataClient`` interfaces:

- :class:`RecordingDataClientWrapper` — sync, returns ``Sequence``
- :class:`RecordingStreamingClientWrapper` — sync generator
- :class:`RecordingAsyncStreamingClientWrapper` — async generator

Recorded items are serialised as NDJSON (one JSON object per line).
Dataclass instances are converted via ``dataclasses.asdict``; everything
else must already be JSON-serialisable (TypedDicts, plain dicts).

The cache directory is created on first write.  If the crawl fails
mid-stream the partial fixture will be absent (data is collected in
memory before being flushed to disk).
"""

from __future__ import annotations

import dataclasses
import json
import logging
from pathlib import Path
from typing import Any, AsyncGenerator, Generator, Generic, Optional, Sequence

from glean.indexing.connectors.base_async_streaming_data_client import BaseAsyncStreamingDataClient
from glean.indexing.connectors.base_data_client import BaseDataClient
from glean.indexing.connectors.base_streaming_data_client import BaseStreamingDataClient
from glean.indexing.models import TSourceData
from glean.indexing.testing.harness.cache.manifest import CacheManifest

logger = logging.getLogger(__name__)

_DATA_FILENAME = "data.ndjson"
_MANIFEST_FILENAME = "manifest.json"


def _serialise(item: Any) -> str:
    """Serialise a single item to a JSON string.

    Handles dataclass instances via ``dataclasses.asdict``; everything else
    must be directly JSON-serialisable.
    """
    if dataclasses.is_dataclass(item) and not isinstance(item, type):
        item = dataclasses.asdict(item)
    return json.dumps(item)


def _write_ndjson(path: Path, items: Sequence[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(_serialise(item) for item in items))


def _sdk_version() -> str:
    try:
        from importlib.metadata import version

        return version("glean-indexing-sdk")
    except Exception:
        return "unknown"


class RecordingDataClientWrapper(BaseDataClient[TSourceData], Generic[TSourceData]):
    """``BaseDataClient`` wrapper that records items to NDJSON on first call.

    Args:
        inner: The real data client to delegate to.
        cache_dir: Directory where the fixture will be written.
        connector_name: Used to namespace the fixture path.
        client_name: Used to namespace the fixture path.
        max_items: Cap the number of recorded items.  ``None`` means no cap.
        sdk_version: Override the SDK version string (primarily for testing).
    """

    def __init__(
        self,
        inner: BaseDataClient[TSourceData],
        cache_dir: Path,
        connector_name: str,
        client_name: str,
        max_items: Optional[int] = None,
        sdk_version: Optional[str] = None,
    ) -> None:
        self._inner = inner
        self._cache_dir = cache_dir
        self._connector_name = connector_name
        self._client_name = client_name
        self._max_items = max_items
        self._sdk_version = sdk_version or _sdk_version()

    def _fixture_dir(self) -> Path:
        return self._cache_dir / self._connector_name / "integration" / self._client_name

    def get_source_data(self, **kwargs: Any) -> Sequence[TSourceData]:
        items: Sequence[TSourceData] = self._inner.get_source_data(**kwargs)
        if self._max_items is not None:
            items = list(items)[: self._max_items]
        else:
            items = list(items)

        fixture_dir = self._fixture_dir()
        data_path = fixture_dir / _DATA_FILENAME
        manifest_path = fixture_dir / _MANIFEST_FILENAME

        _write_ndjson(data_path, items)
        manifest = CacheManifest.create(
            connector=self._connector_name,
            client=self._client_name,
            sdk_version=self._sdk_version,
            item_count=len(items),
        )
        manifest.save(manifest_path)
        logger.debug(
            "Recorded %d items for client '%s' → %s", len(items), self._client_name, data_path
        )
        return items


class RecordingStreamingClientWrapper(BaseStreamingDataClient[TSourceData], Generic[TSourceData]):
    """``BaseStreamingDataClient`` wrapper that records items to NDJSON.

    All items are collected into memory before writing, so the generator is
    fully consumed on the first call.

    Args:
        inner: The real streaming data client to delegate to.
        cache_dir: Directory where the fixture will be written.
        connector_name: Used to namespace the fixture path.
        client_name: Used to namespace the fixture path.
        max_items: Cap the number of recorded items.  ``None`` means no cap.
        sdk_version: Override the SDK version string (primarily for testing).
    """

    def __init__(
        self,
        inner: BaseStreamingDataClient[TSourceData],
        cache_dir: Path,
        connector_name: str,
        client_name: str,
        max_items: Optional[int] = None,
        sdk_version: Optional[str] = None,
    ) -> None:
        self._inner = inner
        self._cache_dir = cache_dir
        self._connector_name = connector_name
        self._client_name = client_name
        self._max_items = max_items
        self._sdk_version = sdk_version or _sdk_version()

    def _fixture_dir(self) -> Path:
        return self._cache_dir / self._connector_name / "integration" / self._client_name

    def get_source_data(self, **kwargs: Any) -> Generator[TSourceData, None, None]:
        items = list(self._inner.get_source_data(**kwargs))
        if self._max_items is not None:
            items = items[: self._max_items]

        fixture_dir = self._fixture_dir()
        data_path = fixture_dir / _DATA_FILENAME
        manifest_path = fixture_dir / _MANIFEST_FILENAME

        _write_ndjson(data_path, items)
        manifest = CacheManifest.create(
            connector=self._connector_name,
            client=self._client_name,
            sdk_version=self._sdk_version,
            item_count=len(items),
        )
        manifest.save(manifest_path)
        logger.debug(
            "Recorded %d items for client '%s' → %s", len(items), self._client_name, data_path
        )
        yield from items


class RecordingAsyncStreamingClientWrapper(
    BaseAsyncStreamingDataClient[TSourceData], Generic[TSourceData]
):
    """``BaseAsyncStreamingDataClient`` wrapper that records items to NDJSON.

    All items are collected from the async generator before writing.

    Args:
        inner: The real async streaming data client to delegate to.
        cache_dir: Directory where the fixture will be written.
        connector_name: Used to namespace the fixture path.
        client_name: Used to namespace the fixture path.
        max_items: Cap the number of recorded items.  ``None`` means no cap.
        sdk_version: Override the SDK version string (primarily for testing).
    """

    def __init__(
        self,
        inner: BaseAsyncStreamingDataClient[TSourceData],
        cache_dir: Path,
        connector_name: str,
        client_name: str,
        max_items: Optional[int] = None,
        sdk_version: Optional[str] = None,
    ) -> None:
        self._inner = inner
        self._cache_dir = cache_dir
        self._connector_name = connector_name
        self._client_name = client_name
        self._max_items = max_items
        self._sdk_version = sdk_version or _sdk_version()

    def _fixture_dir(self) -> Path:
        return self._cache_dir / self._connector_name / "integration" / self._client_name

    async def get_source_data(self, **kwargs: Any) -> AsyncGenerator[TSourceData, None]:
        items = []
        async for item in self._inner.get_source_data(**kwargs):
            items.append(item)
            if self._max_items is not None and len(items) >= self._max_items:
                break

        fixture_dir = self._fixture_dir()
        data_path = fixture_dir / _DATA_FILENAME
        manifest_path = fixture_dir / _MANIFEST_FILENAME

        _write_ndjson(data_path, items)
        manifest = CacheManifest.create(
            connector=self._connector_name,
            client=self._client_name,
            sdk_version=self._sdk_version,
            item_count=len(items),
        )
        manifest.save(manifest_path)
        logger.debug(
            "Recorded %d items for client '%s' → %s", len(items), self._client_name, data_path
        )
        for item in items:
            yield item
