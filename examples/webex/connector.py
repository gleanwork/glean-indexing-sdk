"""Glean-side push logic for the Webex connector.

Maps tagged Webex records to Glean ``DocumentDefinition`` s with email-based
per-document ACLs, and declares the ``webex`` custom datasource. Uses the
streaming base class, so ``index_data()`` batches uploads through
``bulk_index_single_batch_upload`` with a shared upload id (full-crawl
semantics: the final batch prunes documents not seen in this crawl).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import List, Optional, Sequence

from glean.api_client.models import (
    ContentDefinition,
    CustomDatasourceConfig,
    DatasourceCategory,
    DatasourceUserDefinition,
    DocCategory,
    DocumentDefinition,
    DocumentPermissionsDefinition,
    ObjectDefinition,
    UserReferenceDefinition,
)

from glean.indexing.connectors import BaseStreamingDatasourceConnector
from glean.indexing.models import ConnectorOptions, IndexingMode
from glean.indexing.push import PushUploader

from data_client import (
    DEFAULT_BASE_URL,
    DEFAULT_LOOKBACK_DAYS,
    WebexDataClient,
)
from models import MessageRecord, SpaceRecord, WebexRecord

logger = logging.getLogger(__name__)

WEBEX_WEB_SPACE_BASE = "https://web.webex.com/spaces"
_TITLE_MAX = 80


class WebexConnector(BaseStreamingDatasourceConnector[WebexRecord]):
    """Indexes Webex spaces and messages into the ``webex`` Glean datasource."""

    configuration: CustomDatasourceConfig = CustomDatasourceConfig(
        name="webex",
        display_name="Webex",
        datasource_category=DatasourceCategory.MESSAGING,
        url_regex=r"https://web\.webex\.com/spaces/.*",
        # ACLs reference members by email, resolved against Glean's known users.
        is_user_referenced_by_email=True,
        object_definitions=[
            ObjectDefinition(
                name="Space",
                display_label="Webex Space",
                doc_category=DocCategory.MESSAGING,
            ),
            ObjectDefinition(
                name="Message",
                display_label="Webex Message",
                doc_category=DocCategory.MESSAGING,
            ),
        ],
    )

    def __init__(self, name: str = "webex", data_client=None):
        # When run in deployment (run.py calls WebexConnector() with no args),
        # self-wire the data client from environment variables / secrets.
        if data_client is None:
            data_client = WebexDataClient(
                access_token=os.environ["WEBEX_ACCESS_TOKEN"],
                base_url=os.environ.get("WEBEX_BASE_URL", DEFAULT_BASE_URL),
                lookback_days=int(
                    os.environ.get("WEBEX_EVENTS_LOOKBACK_DAYS", str(DEFAULT_LOOKBACK_DAYS))
                ),
            )
        super().__init__(name, data_client)
        self.batch_size = 100
        # Treat the datasource as a test datasource unless explicitly disabled.
        self._is_test = os.environ.get("WEBEX_TEST_DATASOURCE", "true").lower() in ("1", "true", "yes")

    def index_data(
        self,
        mode: IndexingMode = IndexingMode.FULL,
        options: Optional[ConnectorOptions] = None,
    ) -> None:
        """Configure the datasource, push member identities, then push documents.

        Order matters: Glean rejects a document whose ACL references a user that
        is not known to the datasource ("please index the user before adding
        permissions"). Because our ACLs are per-document ``allowed_users`` by
        email, we must push those members as datasource users first. The streaming
        base's ``index_data`` is content-only and does not do this, so we override
        it: run one crawl, push the members seen, then push the documents.
        """
        self.configure_datasource(is_test=self._is_test)

        # One crawl; records are bounded by the rolling ~90-day window.
        records = list(self.data_client.get_source_data())

        members = self.data_client.members
        if members:
            users = [
                DatasourceUserDefinition(email=email, name=name or email)
                for email, name in members.items()
            ]
            logger.info("Indexing %d Webex member(s) as datasource users", len(users))
            PushUploader(datasource=self.name).bulk_index_users(
                users=users, batch_size=self.batch_size
            )

        documents = self.transform(records)
        logger.info("Indexing %d document(s)", len(documents))
        if documents:
            PushUploader(
                datasource=self.name,
                observability=self._observability,
            ).bulk_index_documents(documents=documents, batch_size=self.batch_size)

    def transform(self, data: Sequence[WebexRecord]) -> List[DocumentDefinition]:
        """Map a batch of tagged records to Glean documents."""
        documents: List[DocumentDefinition] = []
        for record in data:
            if record["kind"] == "space":
                documents.append(self._space_document(record))
            else:
                documents.append(self._message_document(record))
        return documents

    # -- per-entity mapping -------------------------------------------------

    def _space_document(self, record: SpaceRecord) -> DocumentDefinition:
        room = record["room"]
        room_id = room["id"]
        title = room.get("title") or "(untitled space)"
        room_type = room.get("type")
        return DocumentDefinition(
            id=f"space:{room_id}",
            datasource=self.name,
            object_type="Space",
            title=title,
            view_url=f"{WEBEX_WEB_SPACE_BASE}/{room_id}",
            body=ContentDefinition(
                mime_type="text/plain",
                text_content=room.get("description") or title,
            ),
            created_at=_epoch_seconds(room.get("created")),
            updated_at=_epoch_seconds(room.get("lastActivity") or room.get("created")),
            permissions=_permissions(record["member_emails"]),
            tags=[room_type] if room_type else None,
        )

    def _message_document(self, record: MessageRecord) -> DocumentDefinition:
        message = record["message"]
        message_id = message["id"]
        room_id = message.get("roomId", "")
        text = message.get("text") or ""
        html = message.get("html")
        author_email = message.get("personEmail")

        if html:
            body = ContentDefinition(mime_type="text/html", text_content=html)
        else:
            body = ContentDefinition(mime_type="text/plain", text_content=text)

        return DocumentDefinition(
            id=f"message:{message_id}",
            datasource=self.name,
            object_type="Message",
            container=f"space:{room_id}",
            title=_message_title(text, record["room_title"]),
            view_url=f"{WEBEX_WEB_SPACE_BASE}/{room_id}",
            body=body,
            author=UserReferenceDefinition(email=author_email) if author_email else None,
            created_at=_epoch_seconds(message.get("created")),
            updated_at=_epoch_seconds(message.get("updated") or message.get("created")),
            permissions=_permissions(record["member_emails"]),
        )


def _permissions(member_emails: Sequence[str]) -> DocumentPermissionsDefinition:
    """Build an email-based ACL. Empty membership fails closed (no viewers)."""
    return DocumentPermissionsDefinition(
        allowed_users=[UserReferenceDefinition(email=email) for email in member_emails]
    )


def _message_title(text: str, room_title: str) -> str:
    snippet = " ".join(text.split())
    if not snippet:
        return f"Message in {room_title}"
    if len(snippet) > _TITLE_MAX:
        return snippet[:_TITLE_MAX].rstrip() + "…"
    return snippet


def _epoch_seconds(timestamp: Optional[str]) -> Optional[int]:
    """Parse a Webex ISO8601 timestamp into Unix seconds; ``None`` if unparseable."""
    if not timestamp:
        return None
    try:
        normalized = timestamp.replace("Z", "+00:00")
        return int(datetime.fromisoformat(normalized).replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        logger.debug("Could not parse timestamp %r", timestamp)
        return None
