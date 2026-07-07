"""Typed source-data models for the Webex connector.

These mirror the fields returned by the Webex REST API (verified live against
https://webexapis.com/v1 on 2026-07-06). Each entity has a small required core
(the fields the connector always relies on) plus optional fields declared via a
``total=False`` subclass.
"""

from __future__ import annotations

from typing import List, Literal, TypedDict, Union


class _RoomRequired(TypedDict):
    """Required fields on a Webex room."""

    id: str


class WebexRoom(_RoomRequired, total=False):
    """A Webex space/room (``GET /rooms`` item)."""

    title: str
    type: str  # "group" | "direct"
    created: str  # ISO-8601
    lastActivity: str  # ISO-8601
    teamId: str
    creatorId: str
    ownerId: str
    isPublic: bool
    isReadOnly: bool
    isLocked: bool


class _MessageRequired(TypedDict):
    """Required fields on a Webex message."""

    id: str


class WebexMessage(_MessageRequired, total=False):
    """A Webex message (``GET /messages`` item)."""

    roomId: str
    roomType: str
    text: str
    html: str
    personId: str
    personEmail: str
    created: str  # ISO-8601
    parentId: str
    files: List[str]
    mentionedPeople: List[str]


class WebexMembership(TypedDict, total=False):
    """A Webex room membership (``GET /memberships`` item)."""

    id: str
    roomId: str
    personId: str
    personEmail: str
    personDisplayName: str
    isModerator: bool


class RoomItem(TypedDict):
    """A room emitted by the data client, carrying its members for permissions."""

    kind: Literal["room"]
    room: WebexRoom
    member_emails: List[str]


class MessageItem(TypedDict):
    """A message emitted by the data client, carrying context for transform."""

    kind: Literal["message"]
    message: WebexMessage
    room_title: str
    member_emails: List[str]


# Discriminated union yielded by WebexDataClient.get_source_data().
WebexItem = Union[RoomItem, MessageItem]
