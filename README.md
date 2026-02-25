# Glean Indexing SDK

[![Prerelease](https://img.shields.io/badge/-Prerelease-F6F3EB?style=flat-square&logo=data:image/svg+xml;base64,PHN2ZyB2aWV3Qm94PSIwIDAgMzIgMzIiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxwYXRoIGQ9Ik0yNC4zMDA2IDIuOTU0MjdMMjAuNzY1NiAwLjE5OTk1MUwxNy45MDI4IDMuOTk1MjdDMTMuNTY1MyAxLjkzNDk1IDguMjMwMTkgMy4wODQzOSA1LjE5Mzk0IDcuMDA5ODNDMS42NTg4OCAxMS41NjQyIDIuNDgzIDE4LjExMzggNy4wMzczOCAyMS42NDg5QzguNzcyMzggMjIuOTkzNSAxMC43ODkzIDIzLjcwOTIgMTIuODI3OSAyMy44MTc3QzE2LjE0NjEgMjQuMDEyOCAxOS41MDc3IDIyLjYyNDggMjEuNjc2NSAxOS44MDU1QzI0LjczNDQgMTUuODggMjQuNTE3NSAxMC40MTQ4IDIxLjQ1OTYgNi43Mjc4OUwyNC4zMDA2IDIuOTU0MjdaTTE4LjExOTcgMTcuMDUxMkMxNi4xMDI4IDE5LjYzMiAxMi4zNzI1IDIwLjEwOTEgOS43NzAwMSAxOC4wOTIyQzcuMTg5MTkgMTYuMDc1MiA2LjcxMjA3IDEyLjMyMzMgOC43MjkwMSA5Ljc0MjQ2QzkuNzA0OTQgOC40ODQ1OCAxMS4xMTQ2IDcuNjgyMTQgMTIuNjc2MSA3LjQ4Njk2QzEzLjA0NDggNy40NDM1OCAxMy40MTM1IDcuNDIxOSAxMy43ODIyIDcuNDQzNThDMTQuOTc1IDcuNTA4NjUgMTYuMTI0NCA3Ljk0MjM5IDE3LjA3ODcgOC42Nzk3N0MxOS42NTk1IDEwLjcxODQgMjAuMTM2NiAxNC40NzAzIDE4LjExOTcgMTcuMDUxMloiIGZpbGw9IndoaXRlIi8+CjxwYXRoIGQ9Ik0yNC41MTc2IDIxLjY5MjJDMjMuOTMyIDIyLjQ1MTMgMjMuMjgxNCAyMy4xMjM2IDIyLjU2NTcgMjMuNzUyNUMyMS44NzE3IDI0LjMzODEgMjEuMTEyNyAyNC44ODAzIDIwLjMxMDIgMjUuMzM1N0MxOS41Mjk1IDI1Ljc2OTUgMTguNjgzNyAyNi4xMzgyIDE3LjgzNzggMjYuNDIwMUMxNi45OTIgMjYuNzAyIDE2LjEwMjggMjYuODk3MiAxNS4yMTM3IDI3LjAwNTdDMTQuMzI0NSAyNy4xMTQxIDEzLjQzNTMgMjcuMTU3NSAxMi41MjQ0IDI3LjA5MjRDMTEuNjEzNSAyNy4wMjczIDEwLjcyNDMgMjYuODc1NSA5Ljg1Njg0IDI2LjY1ODdMOS42NjE2NSAyNy4zNzQzTDguNzcyNDYgMzAuOTk2MkM5LjkwMDIxIDMxLjI5OTggMTEuMDQ5NyAzMS40NzMzIDEyLjIyMDggMzEuNTZDMTIuMjY0MiAzMS41NiAxMi4zMjkyIDMxLjU2IDEyLjM3MjYgMzEuNTZDMTMuNTAwMyAzMS42MjUxIDE0LjY0OTggMzEuNTgxNyAxNS43NTU4IDMxLjQ1MTZDMTYuOTI3IDMxLjI5OTggMTguMDk4MSAzMS4wMzk1IDE5LjIyNTggMzAuNjcwOEMyMC4zNTM2IDMwLjMwMjIgMjEuNDU5NyAyOS44MjUgMjIuNTAwNyAyOS4yMzk1QzIzLjU2MzQgMjguNjUzOSAyNC41NjEgMjcuOTM4MiAyNS40OTM1IDI3LjE1NzVDMjYuNDQ3OCAyNi4zNTUgMjcuMzE1MyAyNS40NDQyIDI4LjA3NDQgMjQuNDQ2NUMyOC4xODI4IDI0LjMxNjQgMjguMjY5NSAyNC4xNjQ2IDI4LjM3OCAyNC4wMTI4TDI0Ljc3NzkgMjEuMzQ1MkMyNC42Njk0IDIxLjQ1MzcgMjQuNjA0NCAyMS41ODM4IDI0LjUxNzYgMjEuNjkyMloiIGZpbGw9IndoaXRlIi8+Cjwvc3ZnPg==&labelColor=343CED)](https://github.com/gleanwork/.github/blob/main/docs/repository-stability.md#prerelease)
[![PyPI version](https://badge.fury.io/py/glean-indexing-sdk.svg)](https://badge.fury.io/py/glean-indexing-sdk)

A Python SDK for building custom Glean indexing connectors. Provides base classes and utilities to create connectors that fetch data from external systems and upload to Glean's indexing APIs.

## Requirements

- Python >= 3.10
- A Glean instance and an [indexing API token](https://developers.glean.com/indexing/tag/Authentication/)

## Installation

```bash
pip install glean-indexing-sdk
```

## Key Concepts

Every connector has two parts:

1. **DataClient** — fetches raw data from your external system (API, database, files)
2. **Connector** — transforms that data into Glean's format and uploads it

The workflow is: **fetch → transform → upload**. You implement `get_source_data()` on your data client and `transform()` on your connector; the SDK handles batching and upload.

See [Architecture overview](docs/architecture.md) for a data flow diagram and the full class hierarchy.

## Quickstart

### 1. Set up credentials

```bash
export GLEAN_INSTANCE="acme"
export GLEAN_INDEXING_API_TOKEN="your-indexing-api-token"
```

### 2. Build a connector

This complete example defines a data type, a data client, and a connector, then indexes everything into Glean:

```python snippet=non_streaming/complete.py
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
```

## Connector Types

| Connector | Data Client | Best For |
|---|---|---|
| [`BaseDatasourceConnector`](docs/advanced.md#basedatasourceconnector) | `BaseDataClient` | Small-to-medium datasets that fit in memory. Wikis, knowledge bases, file systems. |
| [`BaseStreamingDatasourceConnector`](docs/streaming-connectors.md#basestreamingdatasourceconnector) | `BaseStreamingDataClient` | Large or paginated datasets where you need to limit memory usage. Uses sync generators. |
| [`BaseAsyncStreamingDatasourceConnector`](docs/streaming-connectors.md#baseasyncstreamingdatasourceconnector) | `BaseAsyncStreamingDataClient` | Large datasets with async APIs (aiohttp, httpx async). Non-blocking I/O. |
| `BasePeopleConnector` | — | Employee and identity data indexing. |

For detailed guidance on choosing between these, see the [decision matrix](docs/advanced.md#choosing-a-connector-type).

## Indexing Modes

- **`IndexingMode.FULL`** — Re-indexes all documents. Use for initial loads or when you need a complete refresh.
- **`IndexingMode.INCREMENTAL`** — Only indexes documents modified since the last crawl. Use for scheduled updates to minimize API calls.

```python
connector.index_data(mode=IndexingMode.FULL)         # full re-index
connector.index_data(mode=IndexingMode.INCREMENTAL)   # only changes since last run
```

## Testing

The SDK includes a `ConnectorTestHarness` that lets you validate your connector without making real API calls. It intercepts uploads and captures the documents your connector produces so you can assert on them.

```python
from glean.indexing.connectors import ConnectorTestHarness

harness = ConnectorTestHarness(connector)
harness.run()

validator = harness.get_validator()
validator.assert_documents_posted(count=2)

# Inspect individual documents
for doc in validator.documents_posted:
    print(doc.title)
```

## Contributing

This project uses [mise](https://mise.jdx.dev/) for toolchain management and `uv` for Python dependencies.

```bash
mise run setup              # create venv and install dependencies
mise run test               # run all tests
mise run lint               # run all linters (ruff, pyright, markdown-code)
mise run lint:fix           # auto-fix lint issues and format code
```

## Next Steps

- [Architecture overview](docs/architecture.md) — data flow diagram and component hierarchy
- [Streaming connectors](docs/streaming-connectors.md) — sync and async streaming walkthroughs
- [Advanced usage](docs/advanced.md) — connector selection guide, forced restart uploads
- [Worker](docs/worker.md) — subprocess for executing connectors via JSON-RPC (used by the Glean MCP server)
