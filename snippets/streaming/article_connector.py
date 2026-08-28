from datetime import datetime
from typing import Sequence

from glean.api_client.models import DocumentPermissionsDefinition
from glean.indexing.connectors import BaseStreamingDatasourceConnector
from glean.indexing.models import (
    ContentDefinition,
    CustomDatasourceConfig,
    DocumentDefinition,
    UserReferenceDefinition,
)

from .article_data import ArticleData
from .article_data_client import LargeKnowledgeBaseClient


class KnowledgeBaseConnector(BaseStreamingDatasourceConnector[ArticleData]):
    """Transforms streamed articles into Glean documents."""

    configuration = CustomDatasourceConfig(
        name="knowledgebase",
        display_name="Knowledge Base",
        url_regex=r"https://kb\.company\.com/.*",
        is_user_referenced_by_email=True,
    )

    def __init__(self, name: str, data_client: LargeKnowledgeBaseClient) -> None:
        super().__init__(name, data_client)
        self.batch_size = 50

    def transform(self, data: Sequence[ArticleData]) -> Sequence[DocumentDefinition]:
        return [
            DocumentDefinition(
                id=article["id"],
                title=article["title"],
                datasource=self.name,
                view_url=article["url"],
                body=ContentDefinition(
                    mime_type="text/html",
                    text_content=article["content"],
                ),
                author=UserReferenceDefinition(email=article["author"]),
                permissions=DocumentPermissionsDefinition(
                    allowed_users=[
                        UserReferenceDefinition(email=email) for email in article["allowed_users"]
                    ]
                ),
                updated_at=int(
                    datetime.fromisoformat(article["updated_at"].replace("Z", "+00:00")).timestamp()
                ),
            )
            for article in data
        ]
