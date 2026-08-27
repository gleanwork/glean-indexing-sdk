from datetime import datetime
from typing import Sequence

from glean.api_client.models import DocumentPermissionsDefinition
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
    """Transforms asynchronously streamed events into Glean documents."""

    configuration = CustomDatasourceConfig(
        name="company_events",
        display_name="Company Events",
        url_regex=r"https://events\.company\.com/.*",
        is_user_referenced_by_email=True,
    )

    def __init__(self, name: str, api_url: str, api_key: str) -> None:
        super().__init__(
            name,
            EventDataClient(api_url=api_url, api_key=api_key),
        )
        self.batch_size = 50

    def transform(self, data: Sequence[EventData]) -> Sequence[DocumentDefinition]:
        return [
            DocumentDefinition(
                id=event["id"],
                title=event["title"],
                datasource=self.name,
                view_url=event["event_url"],
                body=ContentDefinition(
                    mime_type="text/plain",
                    text_content=event["description"],
                ),
                author=UserReferenceDefinition(email=event["organizer"]),
                permissions=DocumentPermissionsDefinition(
                    allowed_users=[
                        UserReferenceDefinition(email=email) for email in event["allowed_users"]
                    ]
                ),
                updated_at=int(
                    datetime.fromisoformat(event["updated_at"].replace("Z", "+00:00")).timestamp()
                ),
            )
            for event in data
        ]
