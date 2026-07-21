"""Webex Messaging connector (org-wide, compliance-events based, full crawl).

Indexes Webex messages across all org spaces into Glean, with per-room
permissions. See `.glean/connector_plan.md` for the confirmed scope.

Design:
  * Content = reconciled messages from the compliance Events API (90-day window).
  * Permissions = one Glean group per Webex room, members from `/memberships`.
  * Identities (users, groups, memberships) are pushed before documents so ACLs
    resolve. `index_data` is overridden to orchestrate this correctly, since
    membership upload is per-group.
  * Full crawl only: documents fully replace prior state (bulk upload drives
    Glean stale-document deletion).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional, Sequence

from glean.api_client.models import (
    ContentDefinition,
    CustomDatasourceConfig,
    DatasourceBulkMembershipDefinition,
    DatasourceGroupDefinition,
    DatasourceUserDefinition,
    DocumentDefinition,
    DocumentPermissionsDefinition,
    ObjectDefinition,
    UserReferenceDefinition,
)
from glean.api_client.models.customdatasourceconfig import DatasourceCategory
from glean.api_client.models.objectdefinition import DocCategory

from glean.indexing.connectors.base_datasource_connector import BaseDatasourceConnector
from glean.indexing.models import ConnectorOptions, IndexingMode
from glean.indexing.observability import ConnectorObservability
from glean.indexing.push import PushUploader

from .data_client import (
    DEFAULT_LOOKBACK_DAYS,
    WEBEX_BASE_URL,
    WebexComplianceDataClient,
)
from .models import WebexMessage

logger = logging.getLogger(__name__)

DATASOURCE_NAME = "webex"
MESSAGE_OBJECT_TYPE = "Message"
WEBEX_SPACE_URL = "https://web.webex.com/spaces/{room_id}"


def _build_config(name: str) -> CustomDatasourceConfig:
    """Build the datasource config for a given datasource name."""
    return CustomDatasourceConfig(
        name=name,
        display_name="Webex",
        datasource_category=DatasourceCategory.MESSAGING,
        url_regex=r"^https://web\.webex\.com/.*",
        object_definitions=[
            ObjectDefinition(
                name=MESSAGE_OBJECT_TYPE,
                display_label="Message",
                doc_category=DocCategory.MESSAGING,
            )
        ],
    )


class WebexConnector(BaseDatasourceConnector[WebexMessage]):
    """Full-crawl Webex Messaging connector (org-wide via compliance events)."""

    # Class-level default (used by connector discovery/tooling). The runtime
    # instance rebuilds this from the resolved datasource name in __init__.
    configuration = _build_config(DATASOURCE_NAME)

    def __init__(
        self,
        data_client: Optional[WebexComplianceDataClient] = None,
        name: Optional[str] = None,
    ) -> None:
        """Initialize the Webex connector.

        Args:
            data_client: The Webex compliance data client. If omitted, one is
                built from environment variables (`WEBEX_ACCESS_TOKEN`, optional
                `WEBEX_BASE_URL`, `WEBEX_LOOKBACK_DAYS`). The no-argument form is
                used by the deployed CronJob entrypoint.
            name: Datasource name. Defaults to `WEBEX_DATASOURCE_NAME` env var,
                else "webex". Override to target a fresh datasource (a disposed
                datasource name cannot be reused in Glean).
        """
        resolved_name = name or os.environ.get("WEBEX_DATASOURCE_NAME", DATASOURCE_NAME)
        observability = ConnectorObservability(resolved_name)
        client: WebexComplianceDataClient
        if data_client is None:
            client = WebexComplianceDataClient(
                access_token=os.environ["WEBEX_ACCESS_TOKEN"],
                base_url=os.environ.get("WEBEX_BASE_URL", WEBEX_BASE_URL),
                lookback_days=int(os.environ.get("WEBEX_LOOKBACK_DAYS", DEFAULT_LOOKBACK_DAYS)),
                observability=observability,
            )
        else:
            client = data_client
        super().__init__(resolved_name, client)
        # Per-instance config so the datasource name is consistent with self.name.
        self.configuration = _build_config(resolved_name)
        # Share a single observability instance across connector and data client.
        self._observability = observability
        self.data_client: WebexComplianceDataClient = client
        self._room_titles: dict[str, str] = {}

    # -- abstract contract ------------------------------------------------

    def get_data(self, since: Optional[str] = None) -> Sequence[WebexMessage]:
        """Fetch the reconciled set of live messages within the coverage window."""
        return self.data_client.get_source_data(since=since)

    def transform(self, data: Sequence[WebexMessage]) -> Sequence[DocumentDefinition]:
        """Map Webex messages to Glean documents with per-room permissions."""
        documents: list[DocumentDefinition] = []
        for message in data:
            message_id = message.get("id")
            room_id = message.get("roomId")
            if not message_id or not room_id:
                continue
            documents.append(self._to_document(message, message_id, room_id))
        return documents

    # -- orchestration ----------------------------------------------------

    def index_data(
        self,
        mode: IndexingMode = IndexingMode.FULL,
        options: Optional[ConnectorOptions] = None,
    ) -> None:
        """Run a full crawl: identities first, then message documents."""
        obs = self._observability
        obs.start_execution()
        force_restart = bool(options.force_restart) if options else False
        timeout_ms = options.upload_timeout_ms if options else None
        disable_stale = bool(options.disable_stale_deletion_check) if options else False
        try:
            logger.info("Starting %s crawl for datasource '%s'", mode.name.lower(), self.name)

            # 0. Ensure the datasource + object types are registered (idempotent
            #    upsert). The deployed CronJob entrypoint calls only index_data,
            #    so configuration happens here rather than as a separate step.
            self.configure_datasource()

            # 1. Content crawl (single compliance-events pass, reconciled).
            obs.start_timer("data_fetch")
            messages = list(self.get_data())
            obs.end_timer("data_fetch")
            logger.info("Fetched %s live messages", len(messages))
            obs.record_metric("items_fetched", len(messages))

            room_ids = sorted({rid for m in messages if (rid := m.get("roomId"))})
            logger.info("Discovered %s rooms in scope", len(room_ids))
            obs.record_metric("rooms_discovered", len(room_ids))

            # 2. Best-effort room titles for display.
            self._room_titles = self.data_client.fetch_room_titles()

            # 3. Build identities from per-room memberships (the ACL source).
            users, groups, group_members = self._build_identities(room_ids)
            obs.record_metric("users_built", len(users))
            obs.record_metric("groups_built", len(groups))

            uploader = PushUploader(
                datasource=self.name,
                timeout_ms=timeout_ms,
                observability=obs,
            )

            # 4. Push identities BEFORE documents so permissions resolve.
            obs.start_timer("identity_upload")
            if users:
                logger.info("Indexing %s users", len(users))
                uploader.bulk_index_users(
                    users, force_restart_upload=True if force_restart else None
                )
            if groups:
                logger.info("Indexing %s groups", len(groups))
                uploader.bulk_index_groups(
                    groups, force_restart_upload=True if force_restart else None
                )
            for group_name, member_ids in group_members.items():
                memberships = [
                    DatasourceBulkMembershipDefinition(member_user_id=pid) for pid in member_ids
                ]
                uploader.bulk_index_memberships(memberships=memberships, group=group_name)
            obs.end_timer("identity_upload")

            # 5. Transform + upload documents (full-crawl replacement).
            obs.start_timer("data_transform")
            documents = list(self.transform(messages))
            obs.end_timer("data_transform")
            logger.info("Transformed %s documents", len(documents))
            obs.record_metric("documents_transformed", len(documents))

            obs.start_timer("data_upload")
            if documents:
                uploader.bulk_index_documents(
                    documents=documents,
                    batch_size=self.batch_size,
                    force_restart_upload=True if force_restart else None,
                    disable_stale_document_deletion_check=True if disable_stale else None,
                )
            else:
                logger.warning(
                    "No documents to index; skipping upload (stale-deletion not triggered)"
                )
            obs.end_timer("data_upload")

            logger.info("Successfully indexed %s documents to Glean", len(documents))
            obs.record_metric("documents_indexed", len(documents))
        except Exception:
            logger.exception("Error during Webex indexing")
            obs.increment_counter("indexing_errors")
            raise
        finally:
            obs.end_execution()

    # -- helpers ----------------------------------------------------------

    def _build_identities(
        self, room_ids: Sequence[str]
    ) -> tuple[
        list[DatasourceUserDefinition],
        list[DatasourceGroupDefinition],
        dict[str, list[str]],
    ]:
        """Fetch per-room memberships and build users, groups, and group members."""
        users: dict[str, DatasourceUserDefinition] = {}
        groups: list[DatasourceGroupDefinition] = []
        group_members: dict[str, list[str]] = {}

        for room_id in room_ids:
            members = self.data_client.fetch_memberships(room_id)
            group_name = self._group_name(room_id)
            groups.append(DatasourceGroupDefinition(name=group_name))
            member_ids: list[str] = []
            for member in members:
                person_id = member.get("personId")
                if not person_id:
                    continue
                member_ids.append(person_id)
                if person_id not in users:
                    email = member.get("personEmail") or ""
                    users[person_id] = DatasourceUserDefinition(
                        email=email,
                        name=member.get("personDisplayName") or email or person_id,
                        user_id=person_id,
                        is_active=True,
                    )
            group_members[group_name] = member_ids

        return list(users.values()), groups, group_members

    def _to_document(
        self, message: WebexMessage, message_id: str, room_id: str
    ) -> DocumentDefinition:
        """Convert one Webex message to a Glean document."""
        room_title = self._room_title(room_id, message.get("roomType", ""))
        author_email = message.get("personEmail") or ""
        author_name = author_email or message.get("personId") or "Unknown"
        created = _epoch(message.get("created"))

        author_ref = UserReferenceDefinition(
            email=author_email,
            datasource_user_id=message.get("personId"),
            name=author_name,
        )

        return DocumentDefinition(
            datasource=self.name,
            object_type=MESSAGE_OBJECT_TYPE,
            id=message_id,
            title=_title(author_name, room_title),
            body=ContentDefinition(mime_type="text/plain", text_content=message.get("text", "")),
            container=room_title,
            view_url=WEBEX_SPACE_URL.format(room_id=room_id),
            author=author_ref,
            created_at=created,
            updated_at=created,
            permissions=DocumentPermissionsDefinition(allowed_groups=[self._group_name(room_id)]),
        )

    def _room_title(self, room_id: str, room_type: str) -> str:
        """Return a display title for a room (best-effort)."""
        title = self._room_titles.get(room_id)
        if title:
            return title
        return "Direct message" if room_type == "direct" else "Webex space"

    @staticmethod
    def _group_name(room_id: str) -> str:
        """Stable Glean group name for a Webex room."""
        return f"webex-room-{room_id}"


def _title(author_name: str, room_title: str, *, limit: int = 120) -> str:
    """Build a concise document title."""
    title = f"{author_name} in {room_title}"
    return title if len(title) <= limit else title[: limit - 1] + "…"


def _epoch(iso: Optional[str]) -> Optional[int]:
    """Parse a Webex ISO-8601 timestamp to epoch seconds."""
    if not iso:
        return None
    try:
        return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None
