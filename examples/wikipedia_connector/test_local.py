"""Local smoke-test for the Wikipedia connector.

Run before deploying to GCP:
    cd examples/wikipedia_connector
    python test_local.py

Hits the real Wikipedia API — no Glean API calls are made.
"""

from __future__ import annotations

import sys
import os

# Allow running from the SDK repo root without installing the package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from glean.indexing.connectors.base_datasource_connector import BaseDatasourceConnector
from glean.indexing.testing import StaticDataClient, TestHarness, TestConfig
from glean.indexing.models import IndexingMode
from connector import WikipediaConnector, WikipediaDataClient, WikiArticle


def test_transform_only():
    """Phase 1: transform a fake article — no network, no Glean API."""
    fake: list[WikiArticle] = [
        {
            "page_id": "42",
            "title": "Python (programming language)",
            "url": "https://en.wikipedia.org/wiki/Python_(programming_language)",
            "summary": "Python is a high-level, general-purpose programming language.",
            "lang": "en",
        }
    ]
    connector = WikipediaConnector.__new__(WikipediaConnector)
    connector.name = "wikipedia"
    connector._data_client = StaticDataClient(fake)

    docs = connector.transform(fake)
    assert len(docs) == 1
    assert docs[0].id == "wiki-en-42"
    assert "Python" in docs[0].title
    print(f"  transform OK — doc id={docs[0].id!r}")


def test_live_fetch():
    """Phase 2: hit the real Wikipedia API and print what comes back."""
    pages = ["Python (programming language)", "Kubernetes"]
    client = WikipediaDataClient(pages=pages)
    articles = client.get_source_data()
    assert len(articles) == 2, f"Expected 2 articles, got {len(articles)}"
    for a in articles:
        print(f"  fetched: {a['title']} ({len(a['summary'])} chars) — {a['url']}")


def test_full_mock_harness():
    """Phase 3: full connector run against MockGleanClient (no cloud)."""
    fake: list[WikiArticle] = [
        {
            "page_id": "1",
            "title": "Kubernetes",
            "url": "https://en.wikipedia.org/wiki/Kubernetes",
            "summary": "Kubernetes is an open-source container orchestration system.",
            "lang": "en",
        },
        {
            "page_id": "2",
            "title": "Terraform",
            "url": "https://en.wikipedia.org/wiki/Terraform_(software)",
            "summary": "Terraform is an infrastructure-as-code tool.",
            "lang": "en",
        },
    ]

    # Construct the connector with a static data client so no HTTP calls happen.
    connector = WikipediaConnector.__new__(WikipediaConnector)
    BaseDatasourceConnector.__init__(
        connector,
        name="wikipedia",
        data_client=StaticDataClient(fake),
    )
    connector.configuration = WikipediaConnector.configuration

    harness = TestHarness(connector=connector, config=TestConfig())
    result = harness.run_full_mock(mode=IndexingMode.FULL)
    result.assert_documents_posted(count=2, datasource="wikipedia")
    print(f"  harness OK — {result.documents_posted} documents posted to mock Glean")


if __name__ == "__main__":
    print("=== 1. Transform test (no network) ===")
    test_transform_only()

    print("\n=== 2. Live Wikipedia fetch ===")
    test_live_fetch()

    print("\n=== 3. Full mock harness ===")
    test_full_mock_harness()

    print("\nAll local tests passed.")
