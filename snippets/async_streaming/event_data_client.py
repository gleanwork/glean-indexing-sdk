from typing import AsyncGenerator

import aiohttp

from glean.indexing.connectors import BaseAsyncStreamingDataClient

from .event_data import EventData


class EventDataClient(BaseAsyncStreamingDataClient[EventData]):
    """Async streaming client that yields events from a paginated API."""

    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.api_key = api_key

    async def get_source_data(self, **kwargs) -> AsyncGenerator[EventData, None]:
        """Stream events one page at a time using async HTTP."""
        page = 1
        page_size = 100

        async with aiohttp.ClientSession() as session:
            while True:
                params = {"page": page, "size": page_size}
                if kwargs.get("since"):
                    params["modified_since"] = kwargs["since"]

                async with session.get(
                    f"{self.api_url}/events",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    params=params,
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

                events = data.get("events", [])
                if not events:
                    break

                for event in events:
                    yield EventData(event)

                if len(events) < page_size:
                    break

                page += 1
