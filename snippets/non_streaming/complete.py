from typing import List, Sequence, TypedDict

from glean.indexing.connectors import BaseConnectorDataClient, BaseDatasourceConnector
from glean.indexing.models import (
    ContentDefinition,
    CustomDatasourceConfig,
    DocumentDefinition,
    IndexingMode,
    UserReferenceDefinition,
)


class WikiPageData(TypedDict):
    id: str
    title: str
    content: str
    author: str
    created_at: str
    updated_at: str
    url: str
    tags: List[str]


class WikiDataClient(BaseConnectorDataClient[WikiPageData]):
    def __init__(self, wiki_base_url: str, api_token: str):
        self.wiki_base_url = wiki_base_url
        self.api_token = api_token

    def get_source_data(self, since=None) -> Sequence[WikiPageData]:
        # Example static data
        return [
            {
                "id": "page_123",
                "title": "Engineering Onboarding Guide",
                "content": "Welcome to the engineering team...",
                "author": "jane.smith@company.com",
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-02-01T14:30:00Z",
                "url": f"{self.wiki_base_url}/pages/123",
                "tags": ["onboarding", "engineering"],
            },
            {
                "id": "page_124",
                "title": "API Documentation Standards",
                "content": "Our standards for API documentation...",
                "author": "john.doe@company.com",
                "created_at": "2024-01-20T09:15:00Z",
                "updated_at": "2024-01-25T16:45:00Z",
                "url": f"{self.wiki_base_url}/pages/124",
                "tags": ["api", "documentation", "standards"],
            },
        ]


class CompanyWikiConnector(BaseDatasourceConnector[WikiPageData]):
    configuration: CustomDatasourceConfig = CustomDatasourceConfig(
        name="company_wiki",
        display_name="Company Wiki",
        url_regex=r"https://wiki\.company\.com/.*",
        trust_url_regex_for_view_activity=True,
        is_user_referenced_by_email=True,
    )

    def transform(self, data: Sequence[WikiPageData]) -> List[DocumentDefinition]:
        documents = []
        for page in data:
            documents.append(
                DocumentDefinition(
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
            )
        return documents

    def _parse_timestamp(self, timestamp_str: str) -> int:
        from datetime import datetime

        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return int(dt.timestamp())


data_client = WikiDataClient(wiki_base_url="https://wiki.company.com", api_token="your-wiki-token")
connector = CompanyWikiConnector(name="company_wiki", data_client=data_client)
connector.configure_datasource()
connector.index_data(mode=IndexingMode.FULL)
