from typing import List, Sequence

from glean.indexing.connectors import BaseDatasourceConnector
from glean.indexing.models import (
    ContentDefinition,
    CustomDatasourceConfig,
    DocumentDefinition,
    UserReferenceDefinition,
)

from .wiki_page_data import WikiPageData


class CompanyWikiConnector(BaseDatasourceConnector[WikiPageData]):
    """Transform and upload your data to Glean."""

    configuration: CustomDatasourceConfig = CustomDatasourceConfig(
        name="company_wiki",
        display_name="Company Wiki",
        url_regex=r"https://wiki\.company\.com/.*",
        trust_url_regex_for_view_activity=True,
        is_user_referenced_by_email=True,
    )

    def transform(self, data: Sequence[WikiPageData]) -> List[DocumentDefinition]:
        """Transform your data to Glean's format."""
        documents = []
        for page in data:
            document = DocumentDefinition(
                id=page["id"],
                title=page["title"],
                datasource=self.name,
                view_url=page["url"],
                body=ContentDefinition(mime_type="text/plain", text_content=page["content"]),
                author=UserReferenceDefinition(email=page["author"]),
                created_at=self._parse_timestamp(page["created_at"]),
                updated_at=self._parse_timestamp(page["updated_at"]),
                tags=page["tags"],
            )
            documents.append(document)
        return documents

    def _parse_timestamp(self, timestamp_str: str) -> int:
        """Convert ISO timestamp to Unix epoch seconds."""
        from datetime import datetime

        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return int(dt.timestamp())
