import asyncio
import os

from glean.indexing.models import IndexingMode

from .event_connector import EventConnector

connector = EventConnector(
    name="company_events",
    api_url="https://events-api.company.com",
    api_key=os.environ["SOURCE_API_TOKEN"],
)
connector.configure_datasource()


async def main() -> None:
    await connector.index_data_async(mode=IndexingMode.FULL)


asyncio.run(main())
