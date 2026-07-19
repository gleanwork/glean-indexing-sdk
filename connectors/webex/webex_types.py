"""Type definitions for Webex source data."""

from typing import List, TypedDict


class WebexMember(TypedDict):
    """A member of a Webex space, used to build document ACLs and index identities."""

    email: str
    name: str


class WebexMessage(TypedDict):
    """A Webex message, enriched with the fields needed to build a Glean document.

    Sourced from the compliance Events API (``GET /events?resource=messages``) and
    enriched with its space title and member emails during fetch.
    """

    id: str
    room_id: str
    room_type: str
    room_title: str
    text: str
    person_id: str
    person_email: str
    created: str  # ISO-8601 timestamp
    member_emails: List[str]  # emails allowed to see the message (space members)
