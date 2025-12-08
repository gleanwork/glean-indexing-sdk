"""Wiki connector implementation."""

from datetime import datetime
from typing import List, Sequence

from glean.indexing.connectors import BaseDatasourceConnector
from glean.indexing.models import (
    ContentDefinition,
    CustomDatasourceConfig,
    DocumentDefinition,
    UserReferenceDefinition,
)
from wiki_connector.models import WikiPageData


class CompanyWikiConnector(BaseDatasourceConnector[WikiPageData]):
    """Connector for indexing company wiki pages into Glean.

    This connector demonstrates the basic pattern for building
    a datasource connector using the Glean Indexing SDK.
    """

    # Datasource configuration - defines how this datasource appears in Glean
    configuration: CustomDatasourceConfig = CustomDatasourceConfig(
        name="company_wiki",
        display_name="Company Wiki",
        url_regex=r"https://wiki\.company\.com/.*",
        trust_url_regex_for_view_activity=True,
        is_user_referenced_by_email=True,
    )

    def transform(self, data: Sequence[WikiPageData]) -> List[DocumentDefinition]:
        """Transform wiki pages to Glean document definitions.

        Args:
            data: Sequence of wiki page data from the data client.

        Returns:
            List of DocumentDefinition objects ready for indexing.
        """
        documents = []

        for page in data:
            document = DocumentDefinition(
                id=page["id"],
                title=page["title"],
                datasource=self.name,
                view_url=page["url"],
                body=ContentDefinition(
                    mime_type="text/plain",
                    text_content=page["content"],
                ),
                author=UserReferenceDefinition(email=page["author"]),
                created_at=self._parse_timestamp(page["created_at"]),
                updated_at=self._parse_timestamp(page["updated_at"]),
                tags=page["tags"],
            )
            documents.append(document)

        return documents

    def _parse_timestamp(self, timestamp_str: str) -> int:
        """Convert ISO timestamp string to Unix epoch seconds.

        Args:
            timestamp_str: ISO format timestamp (e.g., "2024-01-15T10:00:00Z").

        Returns:
            Unix epoch timestamp in seconds.
        """
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return int(dt.timestamp())
