"""HTTP-based streaming data client helpers for pull recipes."""

import time
from collections.abc import Callable, Generator, Mapping
from typing import Any, Generic, Literal, cast

import httpx

from glean.indexing.connectors.base_streaming_data_client import BaseStreamingDataClient
from glean.indexing.models import TSourceData
from recipes.pull.http_client import PullHttpClient
from recipes.pull.options import PullOptions
from recipes.pull.response import PullResponse

PullPaginationMode = Literal["link", "offset", "cursor", "none"]


class BasePullHttpStreamingDataClient(BaseStreamingDataClient[TSourceData], Generic[TSourceData]):
    """Base class for streaming data clients backed by `PullHttpClient`.

    This handles common JSON-list extraction from HTTP APIs. Subclasses can still
    override `get_source_data` for source-specific behavior.
    """

    def __init__(
        self,
        *,
        base_url: str,
        path: str,
        items_key: str | None = "items",
        pagination: PullPaginationMode = "link",
        params: Mapping[str, Any] | None = None,
        page_size: int | None = None,
        offset_param: str = "offset",
        limit_param: str = "limit",
        start_offset: int = 0,
        cursor_param: str = "cursor",
        cursor_key: str = "next_cursor",
        initial_cursor: str | None = None,
        headers: Mapping[str, str] | None = None,
        options: PullOptions | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        timeout_seconds: float | None = None,
    ) -> None:
        """Initialize the shared pull HTTP client."""
        if pagination == "offset" and (page_size is None or page_size <= 0):
            msg = "page_size must be positive for offset pagination"
            raise ValueError(msg)

        self.path = path
        self.items_key = items_key
        self.pagination = pagination
        self.params = dict(params or {})
        self.page_size = page_size
        self.offset_param = offset_param
        self.limit_param = limit_param
        self.start_offset = start_offset
        self.cursor_param = cursor_param
        self.cursor_key = cursor_key
        self.initial_cursor = initial_cursor
        self.timeout_seconds = timeout_seconds
        self.http = PullHttpClient(
            base_url=base_url,
            headers=headers,
            options=options,
            client=client,
            sleep=sleep,
        )

    def get_source_data(self, **kwargs: Any) -> Generator[TSourceData, None, None]:
        """Yield source data from the configured HTTP endpoint."""
        params = self._params(kwargs)

        if self.pagination == "link":
            for response in self.http.paginate(self.path, params=params, timeout_seconds=self.timeout_seconds):
                yield from self._items(response)
            return

        if self.pagination == "offset":
            yield from self._offset_items(params)
            return

        if self.pagination == "cursor":
            yield from self._cursor_items(params)
            return

        response = self.http.get(self.path, params=params, timeout_seconds=self.timeout_seconds)
        yield from self._items(response)

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self.http.close()

    def _params(self, extra_params: Mapping[str, Any]) -> dict[str, Any]:
        params = dict(self.params)
        params.update(extra_params)
        if self.pagination != "offset" and self.page_size is not None:
            params.setdefault(self.limit_param, self.page_size)
        return params

    def _offset_items(self, base_params: Mapping[str, Any]) -> Generator[TSourceData, None, None]:
        offset = self.start_offset
        page_size = cast(int, self.page_size)

        while True:
            params = dict(base_params)
            params[self.limit_param] = page_size
            params[self.offset_param] = offset
            items = self._items(self.http.get(self.path, params=params, timeout_seconds=self.timeout_seconds))
            if not items:
                return

            yield from items
            if len(items) < page_size:
                return
            offset += page_size

    def _cursor_items(self, base_params: Mapping[str, Any]) -> Generator[TSourceData, None, None]:
        cursor = self.initial_cursor

        while True:
            params = dict(base_params)
            if cursor:
                params[self.cursor_param] = cursor

            response = self.http.get(self.path, params=params, timeout_seconds=self.timeout_seconds)
            yield from self._items(response)

            next_cursor = response.json_dict().get(self.cursor_key)
            if not isinstance(next_cursor, str) or not next_cursor or next_cursor == cursor:
                return
            cursor = next_cursor

    def _items(self, response: PullResponse) -> list[TSourceData]:
        data = response.json_list() if self.items_key is None else response.json_dict().get(self.items_key, [])
        if not isinstance(data, list):
            msg = f"Expected `{self.items_key}` to be a list, got {type(data).__name__}"
            raise TypeError(msg)
        return cast(list[TSourceData], data)
