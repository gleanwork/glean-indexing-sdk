from typing import TypedDict


class EventData(TypedDict):
    """Event returned by the source API."""

    id: str
    title: str
    description: str
    organizer: str
    allowed_users: list[str]
    event_url: str
    updated_at: str
