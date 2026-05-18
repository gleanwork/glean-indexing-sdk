"""Webex connector snippet using the SDK pull and push layers."""

import os
from datetime import datetime
from typing import Sequence

from glean.api_client.models import (
    ContentDefinition,
    DatasourceBulkMembershipDefinition,
    DatasourceCategory,
    DatasourceGroupDefinition,
    DatasourceUserDefinition,
    DocumentDefinition,
    DocumentPermissionsDefinition,
    ObjectDefinition,
    UserReferenceDefinition,
)
from glean.api_client.models.objectdefinition import DocCategory
from glean.indexing.connectors import BaseDatasourceConnector
from glean.indexing.models import (
    ConnectorOptions,
    CustomDatasourceConfig,
    DatasourceIdentityDefinitions,
    IndexingMode,
)
from glean.indexing.push.options import push_options_from_connector_options
from glean.indexing.push.uploader import PushUploader
from glean.indexing.common import api_client

from snippets.webex.checkpoint import FileCheckpointStore
from snippets.webex.data_client import WebexDataClient
from snippets.webex.models import WebexCrawlData, WebexMessage, WebexRoom
from snippets.webex.urls import message_view_url, room_view_url

WEBEX_OBJECT_TYPE_ROOM = "room"
WEBEX_OBJECT_TYPE_MESSAGE = "message"


class WebexConnector(BaseDatasourceConnector[WebexCrawlData]):
    """MVP Webex connector built from SDK pull and push primitives."""

    configuration = CustomDatasourceConfig(
        name="webex",
        display_name="Webex",
        datasource_category=DatasourceCategory.MESSAGING,
        object_definitions=[
            ObjectDefinition(
                name=WEBEX_OBJECT_TYPE_ROOM,
                display_label="Room",
                doc_category=DocCategory.MESSAGING,
            ),
            ObjectDefinition(
                name=WEBEX_OBJECT_TYPE_MESSAGE,
                display_label="Message",
                doc_category=DocCategory.MESSAGING,
            ),
        ],
        url_regex=r"https://web\.webex\.com/.*",
        trust_url_regex_for_view_activity=True,
        is_user_referenced_by_email=False,
    )

    def __init__(
        self,
        name: str,
        data_client: WebexDataClient,
        checkpoint_store: FileCheckpointStore | None = None,
    ):
        """Initialize the Webex connector."""
        super().__init__(name=name, data_client=data_client)
        self.configuration = self.configuration.model_copy(
            update={"name": name, "display_name": name.title()}
        )
        self.webex_data_client = data_client
        self.checkpoint_store = checkpoint_store

    def get_identities(self) -> DatasourceIdentityDefinitions:
        """Fetch Webex users, rooms/teams as groups, and memberships."""
        crawl = self.webex_data_client.fetch(since=self._get_last_crawl_timestamp())
        users, groups, memberships_by_group = _identity_payload(crawl)

        return DatasourceIdentityDefinitions(
            users=users,
            groups=groups,
            memberships=[
                membership
                for memberships in memberships_by_group.values()
                for membership in memberships
            ],
        )

    def transform(self, data: Sequence[WebexCrawlData]) -> Sequence[DocumentDefinition]:
        """Convert fetched Webex data into Glean document definitions."""
        documents: list[DocumentDefinition] = []
        for crawl in data:
            documents.extend(_room_document(room, self.name) for room in crawl.rooms if room.id)
            for room in crawl.rooms:
                messages = crawl.messages_by_room.get(room.id, [])
                documents.extend(_message_thread_documents(room, messages, self.name))
        return documents

    def index_data(
        self,
        mode: IndexingMode = IndexingMode.FULL,
        options: ConnectorOptions | None = None,
    ) -> None:
        """Run a Webex crawl and push identities plus documents.

        This overrides the base identity flow because the current v1
        `bulkindexmemberships` API expects memberships to be uploaded per group.
        """
        since = self._get_last_crawl_timestamp() if mode == IndexingMode.INCREMENTAL else None
        crawl = self.webex_data_client.fetch(since=since)
        push_options = push_options_from_connector_options(options)
        uploader = PushUploader(api_client)

        users, groups, memberships_by_group = _identity_payload(crawl)
        if users:
            uploader.upload_users(
                datasource=self.name, users=users, batch_size=self.batch_size, options=push_options
            )
        if groups:
            uploader.upload_groups(
                datasource=self.name,
                groups=groups,
                batch_size=self.batch_size,
                options=push_options,
            )
        for group_name, memberships in memberships_by_group.items():
            if memberships:
                uploader.upload_memberships(
                    datasource=self.name,
                    memberships=memberships,
                    batch_size=self.batch_size,
                    options=push_options,
                    group=group_name,
                )

        documents = self.transform([crawl])
        if documents:
            uploader.upload_documents(
                datasource=self.name,
                documents=documents,
                batch_size=self.batch_size,
                options=push_options,
            )
        self._save_last_crawl_timestamp(crawl)

    def _get_last_crawl_timestamp(self) -> str | None:
        """Return an optional Webex incremental cursor."""
        if self.checkpoint_store:
            return self.checkpoint_store.read_last_activity_cursor()
        return os.getenv("WEBEX_LAST_ACTIVITY_CURSOR")

    def _save_last_crawl_timestamp(self, crawl: WebexCrawlData) -> None:
        """Persist the high-water mark after a successful push."""
        if not self.checkpoint_store:
            return
        cursor = _latest_room_activity(crawl.rooms)
        if cursor:
            self.checkpoint_store.write_last_activity_cursor(cursor)


def _primary_email(emails: Sequence[str]) -> str | None:
    return emails[0] if emails else None


def _identity_payload(
    crawl: WebexCrawlData,
) -> tuple[
    list[DatasourceUserDefinition],
    list[DatasourceGroupDefinition],
    dict[str, list[DatasourceBulkMembershipDefinition]],
]:
    users = [
        DatasourceUserDefinition(
            email=email,
            name=person.display_name or person.nick_name or email,
            user_id=person.id,
            is_active=(person.status or "active").lower() != "inactive",
        )
        for person in crawl.people
        if person.id and (email := _primary_email(person.emails))
    ]
    groups = [DatasourceGroupDefinition(name=team.id) for team in crawl.teams if team.id]
    groups.extend(
        DatasourceGroupDefinition(name=room.id)
        for room in crawl.rooms
        if room.id and not room.is_public
    )
    memberships_by_group = {
        group_name: _bulk_memberships(members)
        for group_name, members in {**crawl.team_memberships, **crawl.room_memberships}.items()
    }
    return users, groups, memberships_by_group


def _bulk_memberships(members: Sequence[object]) -> list[DatasourceBulkMembershipDefinition]:
    out: list[DatasourceBulkMembershipDefinition] = []
    for member in members:
        person_id = getattr(member, "person_id", None)
        if person_id:
            out.append(DatasourceBulkMembershipDefinition(member_user_id=str(person_id)))
    return out


def _latest_room_activity(rooms: Sequence[WebexRoom]) -> str | None:
    values = [room.last_activity for room in rooms if room.last_activity]
    return max(values) if values else None


def _room_document(room: WebexRoom, datasource: str) -> DocumentDefinition:
    body = (
        ContentDefinition(mime_type="text/plain", text_content=room.description)
        if room.description
        else None
    )
    permissions = (
        DocumentPermissionsDefinition(allow_anonymous_access=True)
        if room.is_public
        else DocumentPermissionsDefinition(allowed_groups=[room.id], allow_anonymous_access=False)
    )
    kwargs = {
        "id": room.id,
        "title": room.title or f"Room {room.id}",
        "datasource": datasource,
        "object_type": WEBEX_OBJECT_TYPE_ROOM,
        "view_url": room_view_url(room.id),
        "container_datasource_id": room.team_id or "",
        "permissions": permissions,
    }
    if body:
        kwargs["body"] = body
    return DocumentDefinition(**kwargs)


def _message_thread_documents(
    room: WebexRoom, messages: Sequence[WebexMessage], datasource: str
) -> list[DocumentDefinition]:
    message_ids = {message.id for message in messages}
    children: dict[str, list[WebexMessage]] = {}
    for message in messages:
        parent_id = message.parent_id or ""
        children.setdefault(parent_id, []).append(message)

    roots = [
        message
        for message in messages
        if not message.parent_id or message.parent_id not in message_ids
    ]
    return [
        doc
        for root in roots
        if (
            doc := _message_thread_document(
                root,
                [root, *sorted(children.get(root.id, []), key=lambda msg: msg.created or "")],
                room,
                datasource,
            )
        )
        is not None
    ]


def _message_thread_document(
    root: WebexMessage,
    thread_messages: Sequence[WebexMessage],
    room: WebexRoom,
    datasource: str,
) -> DocumentDefinition | None:
    if not root.id or not thread_messages:
        return None

    body_parts: list[str] = []
    latest_timestamp = 0
    for message in thread_messages:
        label = (
            "[Message]"
            if message.id == root.id
            else f"[Reply by {message.person_email or message.person_id or 'unknown'}]"
        )
        body_parts.append(f"{label}\n{_message_text(message)}")
        latest_timestamp = max(
            latest_timestamp,
            _parse_timestamp(message.updated) or _parse_timestamp(message.created) or 0,
        )

    permissions = (
        DocumentPermissionsDefinition(allow_anonymous_access=True)
        if room.is_public
        else DocumentPermissionsDefinition(allowed_groups=[room.id], allow_anonymous_access=False)
    )
    root_text = _message_text(root)
    created_at = _parse_timestamp(root.created) or 0
    return DocumentDefinition(
        id=root.id,
        title=root_text[:80] + ("..." if len(root_text) > 80 else ""),
        datasource=datasource,
        object_type=WEBEX_OBJECT_TYPE_MESSAGE,
        view_url=message_view_url(root.room_id, root.id),
        container_datasource_id=root.room_id,
        body=ContentDefinition(mime_type="text/plain", text_content="\n\n---\n\n".join(body_parts)),
        author=UserReferenceDefinition(datasource_user_id=root.person_id)
        if root.person_id
        else None,
        permissions=permissions,
        created_at=created_at,
        updated_at=latest_timestamp or created_at,
    )


def _message_text(message: WebexMessage) -> str:
    return message.text or message.markdown or (message.html or "")[:2000] or "(no content)"


def _parse_timestamp(value: str | None) -> int | None:
    if not value:
        return None
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
