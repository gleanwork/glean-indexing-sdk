"""Wikipedia connector — fetches a small set of Wikipedia articles and indexes them into Glean.

This connector is designed as a self-contained deployment test. It crawls a fixed
list of articles (configurable via WIKIPEDIA_PAGES env var) using the Wikipedia
public REST API and uploads them to Glean as documents.

No authentication is required for the Wikipedia API. The only secrets needed are
the standard Glean credentials (GLEAN_SERVER_URL, GLEAN_INDEXING_API_TOKEN).

Environment variables
---------------------
WIKIPEDIA_PAGES (optional)
    Comma-separated list of Wikipedia article titles to crawl.
    Defaults to a small built-in list when not set.
WIKIPEDIA_LANG (optional)
    Language edition to use (default: "en").
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional, Sequence, TypedDict

import requests

from glean.api_client.models import ContentDefinition, DocumentDefinition
from glean.indexing.connectors.base_datasource_connector import BaseDatasourceConnector
from glean.indexing.connectors.base_data_client import BaseDataClient
from glean.indexing.models import CustomDatasourceConfig, IndexingMode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default article list — enough to exercise the full pipeline without noise.
# ---------------------------------------------------------------------------

DEFAULT_PAGES = [
    "Python (programming language)",
    "Kubernetes",
    "Terraform (software)",
    "Google Kubernetes Engine",
    "Information retrieval",
]

WIKIPEDIA_API = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"


# ---------------------------------------------------------------------------
# Data type
# ---------------------------------------------------------------------------


class WikiArticle(TypedDict):
    page_id: str
    title: str
    url: str
    summary: str
    lang: str


# ---------------------------------------------------------------------------
# Data client
# ---------------------------------------------------------------------------


class WikipediaDataClient(BaseDataClient[WikiArticle]):
    """Fetches Wikipedia article summaries via the public REST API.

    Args:
        pages: Article titles to fetch. Defaults to ``DEFAULT_PAGES``.
        lang: Wikipedia language edition (default ``"en"``).
    """

    def __init__(
        self,
        pages: Optional[List[str]] = None,
        lang: str = "en",
    ) -> None:
        self._pages = pages or DEFAULT_PAGES
        self._lang = lang
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "glean-indexing-sdk-test/1.0"})

    def get_source_data(self, **kwargs) -> Sequence[WikiArticle]:  # type: ignore[override]
        results: List[WikiArticle] = []
        for title in self._pages:
            encoded = requests.utils.quote(title.replace(" ", "_"), safe="")
            url = WIKIPEDIA_API.format(lang=self._lang, title=encoded)
            try:
                resp = self._session.get(url, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                results.append(
                    WikiArticle(
                        page_id=str(data.get("pageid", title)),
                        title=data.get("title", title),
                        url=data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                        summary=data.get("extract", ""),
                        lang=self._lang,
                    )
                )
                logger.info("Fetched: %s", data.get("title", title))
            except requests.RequestException as exc:
                logger.warning("Failed to fetch %r: %s", title, exc)
        return results


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


class WikipediaConnector(BaseDatasourceConnector[WikiArticle]):
    """Glean connector that indexes Wikipedia article summaries.

    Reads ``WIKIPEDIA_PAGES`` and ``WIKIPEDIA_LANG`` from the environment,
    falling back to the defaults defined in this module.

    Example::

        connector = WikipediaConnector()
        connector.index_data(mode=IndexingMode.FULL)
    """

    configuration = CustomDatasourceConfig(
        name="wikipedia",
        display_name="Wikipedia",
        datasource_category="PUBLISHED_CONTENT",
        url_regex="https://.*\\.wikipedia\\.org/wiki/.*",
        object_definitions=[],
    )

    def __init__(self) -> None:
        pages_env = os.environ.get("WIKIPEDIA_PAGES", "")
        pages = [p.strip() for p in pages_env.split(",") if p.strip()] or None
        lang = os.environ.get("WIKIPEDIA_LANG", "en")
        super().__init__(
            name="wikipedia",
            data_client=WikipediaDataClient(pages=pages, lang=lang),
        )

    def transform(self, data: Sequence[WikiArticle]) -> List[DocumentDefinition]:
        docs: List[DocumentDefinition] = []
        for article in data:
            docs.append(
                DocumentDefinition(
                    id=f"wiki-{article['lang']}-{article['page_id']}",
                    title=article["title"],
                    datasource="wikipedia",
                    view_url=article["url"],
                    body=ContentDefinition(
                        mime_type="text/plain",
                        text_content=article["summary"],
                    ),
                )
            )
        return docs
