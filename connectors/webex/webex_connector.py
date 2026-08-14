"""Webex message connector.

Transforms org-wide Webex messages into Glean documents, permission-trimmed to the
members of each message's space. Full-crawl only (see ``.glean/connector_plan.md``).

Because permission-trimmed documents reference ACL users, those users must be indexed
*before* the documents. Streaming connectors do not call ``get_identities()`` on their
own, so this connector indexes ACL users up front in an ``index_data`` override, with a
per-batch safety net for users discovered mid-crawl.
"""

import logging
from datetime import datetime
from typing import List, Optional, Sequence

from glean.api_client.models.customdatasourceconfig import DatasourceCategory
from glean.api_client.models.datasourceuserdefinition import DatasourceUserDefinition
from glean.api_client.models.documentpermissionsdefinition import DocumentPermissionsDefinition
from glean.api_client.models.userreferencedefinition import UserReferenceDefinition

from glean.indexing.connectors import BaseStreamingDatasourceConnector
from glean.indexing.models import (
    ConnectorOptions,
    ContentDefinition,
    CustomDatasourceConfig,
    DatasourceIdentityDefinitions,
    DocumentDefinition,
    IndexingMode,
)
from glean.indexing.push import PushUploader

from .webex_client import WebexComplianceClient
from .webex_types import WebexMessage

logger = logging.getLogger(__name__)

# Best-effort deep link to the space in the Webex web client. Webex has no stable
# public per-message URL; the space URL is the closest navigable target.
_SPACE_URL_TEMPLATE = "https://web.webex.com/spaces/{room_id}"
_TITLE_MAX_LEN = 80


class WebexConnector(BaseStreamingDatasourceConnector[WebexMessage]):
    """Indexes Webex messages into a Glean custom datasource."""

    configuration: CustomDatasourceConfig = CustomDatasourceConfig(
        name="webex",
        display_name="Webex",
        datasource_category=DatasourceCategory.MESSAGING,
        url_regex=r"https://web\.webex\.com/.*",
        is_user_referenced_by_email=True,
    )

    def __init__(self, name: str, data_client: WebexComplianceClient):
        super().__init__(name, data_client)
        self.batch_size = 200
        self._webex_client = data_client
        # None until a real crawl indexes the ACL users; keeps transform() pure for tests.
        self._indexed_emails: Optional[set[str]] = None
        # Keep the registered datasource name and the per-document datasource in sync
        # with the connector's name, so a caller can override "webex" (e.g. for a dev
        # instance where that name is taken) without the two drifting apart.
        if name != self.configuration.name:
            self.configuration = self.configuration.model_copy(update={"name": name})

    def get_identities(self) -> DatasourceIdentityDefinitions:
        """Return the ACL users to index (members of every active space).

        These must be indexed before documents reference them; see ``index_data``.
        """
        users = [
            DatasourceUserDefinition(email=member["email"], name=member["name"])
            for member in self._webex_client.collect_users()
        ]
        return DatasourceIdentityDefinitions(users=users)

    def index_data(
        self,
        mode: IndexingMode = IndexingMode.FULL,
        options: Optional[ConnectorOptions] = None,
    ) -> None:
        """Index ACL users first, then stream messages as documents.

        The streaming base class does not call ``get_identities()``, so non-anonymous
        document permissions would otherwise be rejected with
        ``400 ... please index the user before adding permissions``.
        """
        identities = self.get_identities()
        users = list(identities.get("users") or [])
        if users:
            logger.info("Indexing %d ACL users before documents", len(users))
            PushUploader(datasource=self.name, observability=self._observability).bulk_index_users(users)
        self._indexed_emails = {u.email for u in users}

        super().index_data(mode=mode, options=options)

    def transform(self, data: Sequence[WebexMessage]) -> List[DocumentDefinition]:
        # Safety net: index any ACL user discovered after the up-front identity pass
        # (e.g. a new space that became active mid-crawl). No-op outside a real crawl,
        # so transform() stays pure for unit tests.
        self._ensure_acl_users_indexed(data)

        documents: List[DocumentDefinition] = []
        for message in data:
            created_epoch = self._parse_timestamp(message.get("created", ""))
            documents.append(
                DocumentDefinition(
                    id=message["id"],
                    datasource=self.name,
                    title=self._title(message),
                    view_url=_SPACE_URL_TEMPLATE.format(room_id=message["room_id"]),
                    container=message.get("room_title") or message["room_id"],
                    body=ContentDefinition(mime_type="text/plain", text_content=message.get("text", "")),
                    author=self._user(message.get("person_email")),
                    created_at=created_epoch,
                    updated_at=created_epoch,
                    permissions=self._permissions(message.get("member_emails", [])),
                )
            )
        return documents

    def _ensure_acl_users_indexed(self, data: Sequence[WebexMessage]) -> None:
        """Index (incrementally) any ACL email not covered by the up-front bulk pass."""
        if self._indexed_emails is None:
            return  # not in a real crawl (e.g. unit test calling transform directly)
        stragglers = {
            email
            for message in data
            for email in message.get("member_emails", [])
            if email and email not in self._indexed_emails
        }
        if not stragglers:
            return
        logger.info("Indexing %d straggler ACL user(s) discovered mid-crawl", len(stragglers))
        uploader = PushUploader(datasource=self.name, observability=self._observability)
        for email in stragglers:
            uploader.index_user(DatasourceUserDefinition(email=email, name=email))
            self._indexed_emails.add(email)

    def _title(self, message: WebexMessage) -> str:
        """Messages have no native title; derive one from space + text snippet."""
        space = message.get("room_title") or "Webex space"
        text = (message.get("text") or "").strip().replace("\n", " ")
        if not text:
            author = message.get("person_email") or "someone"
            return f"Message from {author} in {space}"
        snippet = text if len(text) <= _TITLE_MAX_LEN else text[: _TITLE_MAX_LEN - 1].rstrip() + "…"
        return f"{space}: {snippet}"

    @staticmethod
    def _permissions(member_emails: List[str]) -> DocumentPermissionsDefinition:
        return DocumentPermissionsDefinition(
            allowed_users=[UserReferenceDefinition(email=email) for email in member_emails]
        )

    @staticmethod
    def _user(email: Optional[str]) -> Optional[UserReferenceDefinition]:
        return UserReferenceDefinition(email=email) if email else None

    @staticmethod
    def _parse_timestamp(timestamp_str: str) -> Optional[int]:
        if not timestamp_str:
            return None
        try:
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            return int(dt.timestamp())
        except ValueError:
            return None
