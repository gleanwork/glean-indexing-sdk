from collections.abc import Generator
from typing import Any

from glean.indexing.recipes.pull import BasePullHttpStreamingDataClient

from .article_data import ArticleData


class LargeKnowledgeBaseClient(BasePullHttpStreamingDataClient[ArticleData]):
    """Streams every article from an offset-paginated source API."""

    def __init__(self, kb_api_url: str, api_key: str) -> None:
        super().__init__(
            base_url=kb_api_url,
            path="/articles",
            items_key=None,
            pagination="offset",
            page_size=100,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def get_source_data(self, **kwargs: Any) -> Generator[ArticleData, None, None]:
        """Yield all articles, mapping SDK checkpoints to source parameters."""
        source_params = dict(kwargs)
        if since := source_params.pop("since", None):
            source_params["modified_since"] = since
        yield from super().get_source_data(**source_params)
