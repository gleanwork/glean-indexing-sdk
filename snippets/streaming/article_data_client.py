from typing import Generator

import requests

from glean.indexing.connectors.base_streaming_data_client import StreamingConnectorDataClient

from .article_data import ArticleData


class LargeKnowledgeBaseClient(StreamingConnectorDataClient[ArticleData]):
    """Streaming client that yields data incrementally."""

    def __init__(self, kb_api_url: str, api_key: str):
        self.kb_api_url = kb_api_url
        self.api_key = api_key

    def get_source_data(self, since=None) -> Generator[ArticleData, None, None]:
        """Stream documents one page at a time to save memory."""
        page = 1
        page_size = 100

        while True:
            params = {"page": page, "size": page_size}
            if since:
                params["modified_since"] = since

            response = requests.get(
                f"{self.kb_api_url}/articles",
                headers={"Authorization": f"Bearer {self.api_key}"},
                params=params,
            )
            response.raise_for_status()

            data = response.json()
            articles = data.get("articles", [])

            if not articles:
                break

            for article in articles:
                yield ArticleData(article)

            if len(articles) < page_size:
                break

            page += 1
