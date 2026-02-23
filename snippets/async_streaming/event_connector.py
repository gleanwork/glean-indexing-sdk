from typing import List, Sequence

from glean.indexing.connectors import BaseAsyncStreamingDatasourceConnector
from glean.indexing.models import (
    ContentDefinition,
    CustomDatasourceConfig,
    DocumentDefinition,
    UserReferenceDefinition,
)

from .event_data import EventData
from .event_data_client import EventDataClient


class EventConnector(BaseAsyncStreamingDatasourceConnector[EventData]):
    configuration: CustomDatasourceConfig = CustomDatasourceConfig(
        name="company_events",
        display_name="Company Events",
        url_regex=r"https://events\.company\.com/.*",
        trust_url_regex_for_view_activity=True,
    )

    def __init__(self, name: str, api_url: str, api_key: str):
        async_client = EventDataClient(api_url=api_url, api_key=api_key)
        super().__init__(name, async_client)
        self.batch_size = 50

    def transform(self, data: Sequence[EventData]) -> List[DocumentDefinition]:
        documents = []
        for event in data:
            documents.append(
                DocumentDefinition(
                    id=event["id"],
                    title=event["title"],
                    datasource=self.name,
                    view_url=event["event_url"],
                    body=ContentDefinition(
                        mime_type="text/plain", text_content=event["description"]
                    ),
                    author=UserReferenceDefinition(email=event["organizer"]),
                    updated_at=self._parse_timestamp(event["updated_at"]),
                )
            )
        return documents

    def _parse_timestamp(self, timestamp_str: str) -> int:
        from datetime import datetime

        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return int(dt.timestamp())
