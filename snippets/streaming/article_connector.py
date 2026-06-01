from typing import List, Sequence

from glean.api_client.models.userreferencedefinition import UserReferenceDefinition

from glean.indexing.connectors import BaseStreamingDatasourceConnector
from glean.indexing.models import ContentDefinition, CustomDatasourceConfig, DocumentDefinition

from .article_data import ArticleData


class KnowledgeBaseConnector(BaseStreamingDatasourceConnector[ArticleData]):
    configuration: CustomDatasourceConfig = CustomDatasourceConfig(
        name="knowledge_base",
        display_name="Knowledge Base",
        url_regex=r"https://kb\.company\.com/.*",
        trust_url_regex_for_view_activity=True,
    )

    def __init__(self, name: str, data_client):
        super().__init__(name, data_client)
        self.batch_size = 50

    def transform(self, data: Sequence[ArticleData]) -> List[DocumentDefinition]:
        documents = []
        for article in data:
            documents.append(
                DocumentDefinition(
                    id=article["id"],
                    title=article["title"],
                    datasource=self.name,
                    view_url=article["url"],
                    body=ContentDefinition(mime_type="text/html", text_content=article["content"]),
                    author=UserReferenceDefinition(email=article["author"]),
                    updated_at=self._parse_timestamp(article["updated_at"]),
                )
            )
        return documents

    def _parse_timestamp(self, timestamp_str: str) -> int:
        from datetime import datetime

        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return int(dt.timestamp())
