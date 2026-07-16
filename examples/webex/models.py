"""Typed record shapes for the Webex connector.

The data client emits a flat stream of *tagged* records so the streaming
connector can transform each one without re-fetching from Webex. Every record
carries the room's ``member_emails`` so ``transform()`` can build per-document
ACLs without another API call.
"""

from __future__ import annotations

from typing import List, Literal, TypedDict, Union


class _MessageRequired(TypedDict):
    """Keys always present on a Webex message we index."""

    id: str


class WebexMessage(_MessageRequired, total=False):
    """A Webex message object (as embedded in an event's ``data`` field)."""

    roomId: str
    roomType: str
    text: str
    html: str
    files: List[str]
    personId: str
    personEmail: str
    parentId: str
    created: str
    updated: str


class _RoomRequired(TypedDict):
    """Keys always present on a Webex room we index."""

    id: str


class WebexRoom(_RoomRequired, total=False):
    """A Webex room (space) object from ``GET /rooms/{id}``."""

    title: str
    type: str
    description: str
    created: str
    lastActivity: str
    creatorId: str
    ownerId: str
    teamId: str


class SpaceRecord(TypedDict):
    """A room to be indexed as a Space document."""

    kind: Literal["space"]
    room: WebexRoom
    member_emails: List[str]


class MessageRecord(TypedDict):
    """A message to be indexed as a Message document."""

    kind: Literal["message"]
    message: WebexMessage
    room_title: str
    member_emails: List[str]


WebexRecord = Union[SpaceRecord, MessageRecord]
"""A tagged record yielded by the data client and consumed by the connector."""
