"""Sample connector for the scheduled workflow example.

This is identical to the basic_workflow connector.
In production, you would import your actual connector.
"""

from datetime import datetime
from typing import List, Optional, Sequence, TypedDict

from glean.indexing.connectors import BaseConnectorDataClient, BaseDatasourceConnector
from glean.indexing.models import (
    ContentDefinition,
    CustomDatasourceConfig,
    DocumentDefinition,
    UserReferenceDefinition,
)


class ArticleData(TypedDict):
    """Sample article data structure."""

    id: str
    title: str
    content: str
    author: str
    updated_at: str
    url: str


class SampleDataClient(BaseConnectorDataClient[ArticleData]):
    """Sample data client with static data for demonstration."""

    def get_source_data(self, since: Optional[str] = None) -> Sequence[ArticleData]:
        """Return sample articles."""
        return [
            {
                "id": "article_001",
                "title": "Getting Started with Temporal",
                "content": "Temporal is a durable execution platform...",
                "author": "engineer@company.com",
                "updated_at": "2024-03-15T10:00:00Z",
                "url": "https://docs.company.com/temporal-guide",
            },
            {
                "id": "article_002",
                "title": "Glean Integration Best Practices",
                "content": "When building Glean connectors, follow these patterns...",
                "author": "platform@company.com",
                "updated_at": "2024-03-16T14:30:00Z",
                "url": "https://docs.company.com/glean-integration",
            },
        ]


class SampleConnector(BaseDatasourceConnector[ArticleData]):
    """Sample connector for the workflow example."""

    configuration: CustomDatasourceConfig = CustomDatasourceConfig(
        name="sample_docs",
        display_name="Sample Documentation",
        url_regex=r"https://docs\.company\.com/.*",
        trust_url_regex_for_view_activity=True,
        is_user_referenced_by_email=True,
    )

    def transform(self, data: Sequence[ArticleData]) -> List[DocumentDefinition]:
        """Transform articles to Glean documents."""
        documents = []
        for article in data:
            documents.append(
                DocumentDefinition(
                    id=article["id"],
                    title=article["title"],
                    datasource=self.name,
                    view_url=article["url"],
                    body=ContentDefinition(
                        mime_type="text/plain",
                        text_content=article["content"],
                    ),
                    author=UserReferenceDefinition(email=article["author"]),
                    updated_at=self._parse_timestamp(article["updated_at"]),
                )
            )
        return documents

    def _parse_timestamp(self, timestamp_str: str) -> int:
        """Convert ISO timestamp to Unix epoch seconds."""
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return int(dt.timestamp())


def create_connector(connector_name: str) -> SampleConnector:
    """Factory function to create a connector by name."""
    data_client = SampleDataClient()
    return SampleConnector(name=connector_name, data_client=data_client)
