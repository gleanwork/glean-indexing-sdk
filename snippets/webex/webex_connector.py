from datetime import datetime
from typing import Sequence

from glean.api_client.models.customdatasourceconfig import DatasourceCategory
from glean.api_client.models.documentpermissionsdefinition import DocumentPermissionsDefinition
from glean.api_client.models.userreferencedefinition import UserReferenceDefinition
from glean.indexing.connectors import BaseStreamingDatasourceConnector
from glean.indexing.models import ContentDefinition, CustomDatasourceConfig, DocumentDefinition

from .webex_data import WebexDocument


class WebexConnector(BaseStreamingDatasourceConnector[WebexDocument]):
    """Streaming connector for Webex Messaging content."""

    configuration: CustomDatasourceConfig = CustomDatasourceConfig(
        name="webex",
        display_name="Webex",
        datasource_category=DatasourceCategory.MESSAGING,
        url_regex=r"^https://(?:app\.)?webex\.com/.*",
        trust_url_regex_for_view_activity=True,
        is_user_referenced_by_email=True,
    )

    def __init__(self, name: str, data_client):
        super().__init__(name, data_client)
        self.batch_size = 50

    def sync_identities(self) -> None:
        """Index Webex users, groups, and memberships before document upload."""
        users, groups, memberships = self.data_client.get_identity_data()
        self.index_users(users)
        self.index_groups(groups)
        self.index_memberships(memberships)

    def transform(self, data: Sequence[WebexDocument]) -> list[DocumentDefinition]:
        documents: list[DocumentDefinition] = []
        for item in data:
            documents.append(
                DocumentDefinition(
                    id=item["id"],
                    title=item["title"],
                    datasource=self.name,
                    view_url=item["url"],
                    body=ContentDefinition(mime_type="text/plain", text_content=item["body"]),
                    author=self._author(item["author_email"]),
                    created_at=self._parse_timestamp(item["created_at"]),
                    updated_at=self._parse_timestamp(item["updated_at"]),
                    permissions=DocumentPermissionsDefinition(
                        allowed_users=[
                            UserReferenceDefinition(email=email)
                            for email in item["allowed_user_emails"]
                        ],
                    ),
                    tags=["webex"],
                )
            )
        return documents

    def _author(self, email: str) -> UserReferenceDefinition | None:
        if not email:
            return None
        return UserReferenceDefinition(email=email)

    def _parse_timestamp(self, timestamp: str) -> int | None:
        if not timestamp:
            return None
        return int(datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp())
