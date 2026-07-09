"""Data-client wrappers that replay items from NDJSON fixtures on disk.

Each wrapper class mirrors one of the three ``Base*DataClient`` interfaces:

- :class:`ReplayDataClientWrapper` — sync, returns ``Sequence``
- :class:`ReplayStreamingClientWrapper` — sync generator
- :class:`ReplayAsyncStreamingClientWrapper` — async generator

Items are deserialised as plain ``dict`` objects.  For connectors whose
``transform()`` operates on ``TypedDict`` instances (which are dicts at
runtime) this is transparent.  For connectors that use proper dataclass
instances in their transform logic, the connector author should ensure
``transform()`` accepts plain dicts (which is typical because data clients
commonly return ``TypedDict`` results anyway).

The NDJSON file must have been produced by the matching ``Recording*Wrapper``.
An empty or missing NDJSON file raises a clear :class:`FileNotFoundError` or
:class:`ValueError` rather than silently returning an empty sequence.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, AsyncGenerator, Generator, Generic, List, Optional, Sequence

from glean.indexing.connectors.base_async_streaming_data_client import BaseAsyncStreamingDataClient
from glean.indexing.connectors.base_data_client import BaseDataClient
from glean.indexing.connectors.base_streaming_data_client import BaseStreamingDataClient
from glean.indexing.models import TSourceData

logger = logging.getLogger(__name__)

_DATA_FILENAME = "data.ndjson"


def _load_ndjson(path: Path) -> List[Any]:
    """Read and parse an NDJSON file.

    Args:
        path: Path to the NDJSON file.

    Returns:
        List of deserialised items.

    Raises:
        FileNotFoundError: If *path* does not exist.
        ValueError: If *path* exists but is empty.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Cache fixture not found: {path}\n"
            "Run the integration test without a cache first to record the fixture."
        )
    content = path.read_text().strip()
    if not content:
        raise ValueError(
            f"Cache fixture is empty: {path}\n"
            "Delete the fixture directory and re-run to re-record."
        )
    return [json.loads(line) for line in content.splitlines()]


class ReplayDataClientWrapper(BaseDataClient[TSourceData], Generic[TSourceData]):
    """``BaseDataClient`` that replays items from a previously recorded NDJSON fixture.

    Args:
        cache_dir: Root cache directory (same value as used during recording).
        connector_name: Connector name (used to locate the fixture path).
        client_name: Data-client attribute name (used to locate the fixture path).
        max_items: If set, replay at most this many items.
    """

    def __init__(
        self,
        cache_dir: Path,
        connector_name: str,
        client_name: str,
        max_items: Optional[int] = None,
    ) -> None:
        self._cache_dir = cache_dir
        self._connector_name = connector_name
        self._client_name = client_name
        self._max_items = max_items

    def _data_path(self) -> Path:
        return (
            self._cache_dir / self._connector_name / "integration" / self._client_name / _DATA_FILENAME
        )

    def get_source_data(self, **kwargs: Any) -> Sequence[TSourceData]:
        path = self._data_path()
        items = _load_ndjson(path)
        if self._max_items is not None:
            items = items[: self._max_items]
        logger.debug(
            "Replayed %d items for client '%s' ← %s", len(items), self._client_name, path
        )
        return items  # type: ignore[return-value]


class ReplayStreamingClientWrapper(BaseStreamingDataClient[TSourceData], Generic[TSourceData]):
    """``BaseStreamingDataClient`` that replays items from a recorded NDJSON fixture.

    Args:
        cache_dir: Root cache directory.
        connector_name: Connector name.
        client_name: Data-client attribute name.
        max_items: If set, replay at most this many items.
    """

    def __init__(
        self,
        cache_dir: Path,
        connector_name: str,
        client_name: str,
        max_items: Optional[int] = None,
    ) -> None:
        self._cache_dir = cache_dir
        self._connector_name = connector_name
        self._client_name = client_name
        self._max_items = max_items

    def _data_path(self) -> Path:
        return (
            self._cache_dir / self._connector_name / "integration" / self._client_name / _DATA_FILENAME
        )

    def get_source_data(self, **kwargs: Any) -> Generator[TSourceData, None, None]:
        path = self._data_path()
        items = _load_ndjson(path)
        if self._max_items is not None:
            items = items[: self._max_items]
        logger.debug(
            "Replayed %d items for client '%s' ← %s", len(items), self._client_name, path
        )
        for item in items:
            yield item  # type: ignore[misc]


class ReplayAsyncStreamingClientWrapper(
    BaseAsyncStreamingDataClient[TSourceData], Generic[TSourceData]
):
    """``BaseAsyncStreamingDataClient`` that replays items from a recorded NDJSON fixture.

    Args:
        cache_dir: Root cache directory.
        connector_name: Connector name.
        client_name: Data-client attribute name.
        max_items: If set, replay at most this many items.
    """

    def __init__(
        self,
        cache_dir: Path,
        connector_name: str,
        client_name: str,
        max_items: Optional[int] = None,
    ) -> None:
        self._cache_dir = cache_dir
        self._connector_name = connector_name
        self._client_name = client_name
        self._max_items = max_items

    def _data_path(self) -> Path:
        return (
            self._cache_dir / self._connector_name / "integration" / self._client_name / _DATA_FILENAME
        )

    async def get_source_data(self, **kwargs: Any) -> AsyncGenerator[TSourceData, None]:
        path = self._data_path()
        items = _load_ndjson(path)
        if self._max_items is not None:
            items = items[: self._max_items]
        logger.debug(
            "Replayed %d items for client '%s' ← %s", len(items), self._client_name, path
        )
        for item in items:
            yield item  # type: ignore[misc]
