"""Sample connector for Docker execution.

Replace this with your actual connector implementation.
"""

import os
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
    """Sample data client for demonstration."""

    def __init__(self):
        """Initialize the data client from environment variables."""
        self.api_url = os.getenv("SOURCE_API_URL", "https://docs.company.com")
        self.api_key = os.getenv("SOURCE_API_KEY", "")

    def get_source_data(self, since: Optional[str] = None) -> Sequence[ArticleData]:
        """Fetch articles from the source system."""
        # In production, call your API here
        return [
            {
                "id": "article_001",
                "title": "Docker Deployment Guide",
                "content": "This guide covers deploying Glean connectors with Docker...",
                "author": "devops@company.com",
                "updated_at": "2024-03-15T10:00:00Z",
                "url": f"{self.api_url}/articles/001",
            },
            {
                "id": "article_002",
                "title": "Container Best Practices",
                "content": "When running connectors in containers, consider these patterns...",
                "author": "platform@company.com",
                "updated_at": "2024-03-16T14:30:00Z",
                "url": f"{self.api_url}/articles/002",
            },
        ]


class SampleConnector(BaseDatasourceConnector[ArticleData]):
    """Sample connector for Docker execution."""

    configuration: CustomDatasourceConfig = CustomDatasourceConfig(
        name="docker_docs",
        display_name="Docker Documentation",
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
