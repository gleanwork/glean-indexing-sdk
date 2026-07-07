"""Webex streaming datasource connector.

Maps Webex spaces and messages onto Glean :class:`DocumentDefinition` objects and
uploads them via the SDK's streaming push path. Each document is restricted to the
members of its room (``allowed_users`` by email).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Sequence

from glean.api_client.models import (
    ContentDefinition,
    DatasourceCategory,
    DocumentDefinition,
    DocumentPermissionsDefinition,
    UserReferenceDefinition,
)
from glean.indexing.connectors import BaseStreamingDataClient, BaseStreamingDatasourceConnector
from glean.indexing.models import CustomDatasourceConfig

from examples.webex.models import WebexItem, WebexMessage, WebexRoom

# Webex web client space deep-link, e.g. https://web.webex.com/spaces/<id>
_SPACE_URL = "https://web.webex.com/spaces/{room_id}"
_MESSAGE_TITLE_MAX = 120


class WebexConnector(BaseStreamingDatasourceConnector[WebexItem]):
    """Indexes Webex group spaces and their messages into Glean."""

    configuration: CustomDatasourceConfig = CustomDatasourceConfig(
        name="webex",
        display_name="Webex",
        datasource_category=DatasourceCategory.MESSAGING,
        url_regex=r"https://web\.webex\.com/.*",
        is_user_referenced_by_email=True,
    )

    def __init__(
        self, data_client: BaseStreamingDataClient[WebexItem], name: str = "webex"
    ) -> None:
        super().__init__(name, data_client)

    def transform(self, data: Sequence[WebexItem]) -> List[DocumentDefinition]:
        """Transform a batch of Webex items into Glean documents."""
        documents: List[DocumentDefinition] = []
        for item in data:
            if item["kind"] == "room":
                documents.append(self._room_to_document(item["room"], item["member_emails"]))
            else:
                documents.append(
                    self._message_to_document(
                        item["message"], item["room_title"], item["member_emails"]
                    )
                )
        return documents

    # -- Mapping helpers --------------------------------------------------

    def _permissions(self, member_emails: Sequence[str]) -> DocumentPermissionsDefinition:
        return DocumentPermissionsDefinition(
            allowed_users=[UserReferenceDefinition(email=email) for email in member_emails]
        )

    def _room_to_document(
        self, room: WebexRoom, member_emails: Sequence[str]
    ) -> DocumentDefinition:
        room_id = room["id"]
        created = _to_epoch(room.get("created"))
        updated = _to_epoch(room.get("lastActivity")) or created
        return DocumentDefinition(
            id=f"room:{room_id}",
            datasource=self.name,
            object_type="Space",
            title=room.get("title") or "Untitled space",
            view_url=_SPACE_URL.format(room_id=room_id),
            body=ContentDefinition(mime_type="text/plain", text_content=room.get("title") or ""),
            created_at=created,
            updated_at=updated,
            permissions=self._permissions(member_emails),
        )

    def _message_to_document(
        self, message: WebexMessage, room_title: str, member_emails: Sequence[str]
    ) -> DocumentDefinition:
        message_id = message["id"]
        text = message.get("text") or ""
        author_email = message.get("personEmail")
        room_id = message.get("roomId", "")
        return DocumentDefinition(
            id=f"message:{message_id}",
            datasource=self.name,
            object_type="Message",
            title=_message_title(author_email, room_title, text),
            container=room_title or room_id,
            view_url=_SPACE_URL.format(room_id=room_id),
            body=ContentDefinition(mime_type="text/plain", text_content=text),
            author=UserReferenceDefinition(email=author_email) if author_email else None,
            created_at=_to_epoch(message.get("created")),
            updated_at=_to_epoch(message.get("created")),
            permissions=self._permissions(member_emails),
        )


def _to_epoch(timestamp: str | None) -> int | None:
    """Convert a Webex ISO-8601 timestamp to epoch seconds, or None."""
    if not timestamp:
        return None
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _message_title(author_email: str | None, room_title: str, text: str) -> str:
    """Build a concise, human-readable title for a message document."""
    who = author_email or "Unknown"
    where = room_title or "a Webex space"
    snippet = " ".join(text.split())
    prefix = f"{who} in {where}"
    if snippet:
        title = f"{prefix}: {snippet}"
    else:
        title = prefix
    if len(title) > _MESSAGE_TITLE_MAX:
        title = title[: _MESSAGE_TITLE_MAX - 1].rstrip() + "…"
    return title
