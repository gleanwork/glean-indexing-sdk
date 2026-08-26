import os
from datetime import datetime
from typing import Any, List, Optional, Sequence, TypedDict

from glean.indexing.connectors import BaseDataClient, BaseDatasourceConnector
from glean.indexing.models import (
    ContentDefinition,
    CustomDatasourceConfig,
    DocumentDefinition,
    IndexingMode,
    UserReferenceDefinition,
)


class WikiPage(TypedDict):
    id: str
    title: str
    content: str
    author: str
    updated_at: str
    url: str


class WikiDataClient(BaseDataClient[WikiPage]):
    """Fetches pages from the source system. Replace the body with a real API call."""

    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url
        self.api_token = api_token

    def get_source_data(self, since: Optional[str] = None, **kwargs: Any) -> Sequence[WikiPage]:
        return [
            {
                "id": "page_123",
                "title": "Engineering Onboarding Guide",
                "content": "Welcome to the engineering team...",
                "author": "jane.smith@company.com",
                "updated_at": "2026-02-01T14:30:00Z",
                "url": f"{self.base_url}/pages/123",
            }
        ]


class CompanyWikiConnector(BaseDatasourceConnector[WikiPage]):
    """Transforms wiki pages into Glean documents."""

    configuration = CustomDatasourceConfig(
        name="company_wiki",
        display_name="Company Wiki",
        url_regex=r"https://wiki\.company\.com/.*",
        is_user_referenced_by_email=True,
    )

    def transform(self, data: Sequence[WikiPage]) -> List[DocumentDefinition]:
        return [
            DocumentDefinition(
                id=page["id"],
                title=page["title"],
                datasource=self.name,
                view_url=page["url"],
                body=ContentDefinition(mime_type="text/plain", text_content=page["content"]),
                author=UserReferenceDefinition(email=page["author"]),
                # created_at / updated_at are epoch seconds, not ISO strings.
                updated_at=int(
                    datetime.fromisoformat(page["updated_at"].replace("Z", "+00:00")).timestamp()
                ),
            )
            for page in data
        ]


def create_connector() -> CompanyWikiConnector:
    """Build the production connector after runtime secrets are loaded."""
    return CompanyWikiConnector(
        name="company_wiki",
        data_client=WikiDataClient(
            base_url="https://wiki.company.com",
            api_token=os.environ["WIKI_API_TOKEN"],
        ),
    )


if __name__ == "__main__":
    connector = create_connector()
    connector.configure_datasource()
    connector.index_data(mode=IndexingMode.FULL)
