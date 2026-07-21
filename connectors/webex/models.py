"""Source-side data types for the Webex compliance connector.

These TypedDicts mirror the fields the connector actually consumes from the
Webex compliance Events API (`event.data`) and the Memberships API. They are
intentionally minimal — only what V1 maps into Glean.
"""

from __future__ import annotations

from typing import TypedDict


class WebexMessage(TypedDict, total=False):
    """A reconciled Webex message, sourced from compliance message events.

    Fields come from `GET /events?resource=messages` -> `item.data`.
    """

    id: str
    roomId: str
    roomType: str  # "group" | "direct"
    text: str
    personId: str
    personEmail: str
    created: str  # ISO-8601, e.g. "2026-06-18T15:34:20.669Z"


class WebexMembership(TypedDict, total=False):
    """A Webex room membership, sourced from `GET /memberships?roomId=`.

    This is the per-room ACL subject.
    """

    id: str
    roomId: str
    personId: str
    personEmail: str
    personDisplayName: str
    isModerator: bool
