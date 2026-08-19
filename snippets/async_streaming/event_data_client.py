import asyncio
from collections.abc import AsyncGenerator
from typing import Any, cast

import httpx

from glean.indexing.connectors import BaseAsyncStreamingDataClient

from .event_data import EventData


class EventDataClient(BaseAsyncStreamingDataClient[EventData]):
    """Streams every event from an async paginated source API."""

    _RETRY_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(self, api_url: str, api_key: str, max_attempts: int = 3) -> None:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.max_attempts = max_attempts

    async def get_source_data(self, **kwargs: Any) -> AsyncGenerator[EventData, None]:
        """Yield all event pages, retrying transient source failures."""
        page = 1
        page_size = 100
        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                params: dict[str, Any] = {"page": page, "size": page_size}
                if since := kwargs.get("since"):
                    params["modified_since"] = since

                response = await self._get_page(client, headers, params)
                payload = response.json()
                if (
                    not isinstance(payload, dict)
                    or "events" not in payload
                    or "next_page" not in payload
                ):
                    raise TypeError("Expected an object containing `events` and `next_page` fields")
                events = payload["events"]
                if not isinstance(events, list):
                    raise TypeError("Expected `events` to be a list")

                for event in events:
                    yield cast(EventData, event)

                next_page = payload.get("next_page")
                if next_page is None:
                    return
                if not isinstance(next_page, int) or next_page <= page:
                    raise TypeError("Expected `next_page` to advance to a later integer page")
                page = next_page

    async def _get_page(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        params: dict[str, Any],
    ) -> httpx.Response:
        for attempt in range(1, self.max_attempts + 1):
            response: httpx.Response | None = None
            try:
                response = await client.get(
                    f"{self.api_url}/events",
                    headers=headers,
                    params=params,
                )
                if response.status_code not in self._RETRY_STATUS_CODES:
                    response.raise_for_status()
                    return response
                if attempt == self.max_attempts:
                    response.raise_for_status()
            except httpx.RequestError:
                if attempt == self.max_attempts:
                    raise

            retry_after = response.headers.get("Retry-After") if response else None
            try:
                delay = max(0.0, float(retry_after)) if retry_after else 2 ** (attempt - 1)
            except ValueError:
                delay = 2 ** (attempt - 1)
            await asyncio.sleep(min(delay, 30.0))

        raise RuntimeError("Unreachable retry state")
