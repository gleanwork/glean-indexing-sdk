from typing import TypedDict


class EventData(TypedDict):
    """Type definition for event data from an async API."""

    id: str
    title: str
    description: str
    organizer: str
    event_url: str
    updated_at: str
