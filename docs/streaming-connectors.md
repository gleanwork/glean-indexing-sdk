# Streaming Connectors

Streaming connectors process data incrementally rather than loading everything into memory at once. The SDK provides two variants:

- **`BaseStreamingDatasourceConnector`** — sync generator-based streaming
- **`BaseAsyncStreamingDatasourceConnector`** — async generator-based streaming

---

## BaseStreamingDatasourceConnector

Use the sync streaming connector when your data source provides synchronous APIs (e.g., `requests`, database cursors) and the dataset is too large to fit in memory.

### Step 1: Define Your Data Type

```python snippet=streaming/article_data.py
from typing import TypedDict


class ArticleData(TypedDict):
    """Type definition for knowledge base article data."""

    id: str
    title: str
    content: str
    author: str
    updated_at: str
    url: str
```

### Step 2: Create Your Streaming DataClient

Implement `get_source_data()` as a generator that yields items one at a time or page at a time.

```python snippet=streaming/article_data_client.py
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
```

### Step 3: Create Your Streaming Connector

```python snippet=streaming/article_connector.py
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
```

### Step 4: Run the Connector

```python snippet=streaming/run_connector.py
from glean.indexing.models import IndexingMode

from .article_connector import KnowledgeBaseConnector
from .article_data_client import LargeKnowledgeBaseClient

data_client = LargeKnowledgeBaseClient(
    kb_api_url="https://kb-api.company.com", api_key="your-kb-api-key"
)
connector = KnowledgeBaseConnector(name="knowledge_base", data_client=data_client)

connector.configure_datasource()
connector.index_data(mode=IndexingMode.FULL)
```

---

## BaseAsyncStreamingDatasourceConnector

Use the async streaming connector when your data source provides async APIs (e.g., `aiohttp`, `httpx` async) and you want non-blocking I/O during data retrieval.

### Step 1: Define Your Data Type

```python snippet=async_streaming/event_data.py
from typing import TypedDict


class EventData(TypedDict):
    """Type definition for event data from an async API."""

    id: str
    title: str
    description: str
    organizer: str
    event_url: str
    updated_at: str
```

### Step 2: Create Your Async Streaming DataClient

Implement `get_source_data()` as an async generator. The `**kwargs` signature accepts a `since` keyword for incremental crawls.

```python snippet=async_streaming/event_data_client.py
from typing import AsyncGenerator

import aiohttp

from glean.indexing.connectors import BaseAsyncStreamingDataClient

from .event_data import EventData


class EventDataClient(BaseAsyncStreamingDataClient[EventData]):
    """Async streaming client that yields events from a paginated API."""

    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.api_key = api_key

    async def get_source_data(self, **kwargs) -> AsyncGenerator[EventData, None]:
        """Stream events one page at a time using async HTTP."""
        page = 1
        page_size = 100

        async with aiohttp.ClientSession() as session:
            while True:
                params = {"page": page, "size": page_size}
                if kwargs.get("since"):
                    params["modified_since"] = kwargs["since"]

                async with session.get(
                    f"{self.api_url}/events",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    params=params,
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

                events = data.get("events", [])
                if not events:
                    break

                for event in events:
                    yield EventData(event)

                if len(events) < page_size:
                    break

                page += 1
```

### Step 3: Create Your Async Connector

Pass the async data client to `super().__init__()`. The `transform()` method works the same as the sync variant.

```python snippet=async_streaming/event_connector.py
from typing import List, Sequence

from glean.indexing.connectors import BaseAsyncStreamingDatasourceConnector
from glean.indexing.models import (
    ContentDefinition,
    CustomDatasourceConfig,
    DocumentDefinition,
    UserReferenceDefinition,
)

from .event_data import EventData
from .event_data_client import EventDataClient


class EventConnector(BaseAsyncStreamingDatasourceConnector[EventData]):
    configuration: CustomDatasourceConfig = CustomDatasourceConfig(
        name="company_events",
        display_name="Company Events",
        url_regex=r"https://events\.company\.com/.*",
        trust_url_regex_for_view_activity=True,
    )

    def __init__(self, name: str, api_url: str, api_key: str):
        async_client = EventDataClient(api_url=api_url, api_key=api_key)
        super().__init__(name, async_client)
        self.batch_size = 50

    def transform(self, data: Sequence[EventData]) -> List[DocumentDefinition]:
        documents = []
        for event in data:
            documents.append(
                DocumentDefinition(
                    id=event["id"],
                    title=event["title"],
                    datasource=self.name,
                    view_url=event["event_url"],
                    body=ContentDefinition(
                        mime_type="text/plain", text_content=event["description"]
                    ),
                    author=UserReferenceDefinition(email=event["organizer"]),
                    updated_at=self._parse_timestamp(event["updated_at"]),
                )
            )
        return documents

    def _parse_timestamp(self, timestamp_str: str) -> int:
        from datetime import datetime

        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return int(dt.timestamp())
```

### Step 4: Run the Connector

Use `index_data_async()` with `await` inside an async context.

```python snippet=async_streaming/run_connector.py
import asyncio

from glean.indexing.models import IndexingMode

from .event_connector import EventConnector

connector = EventConnector(
    name="company_events",
    api_url="https://events-api.company.com",
    api_key="your-events-api-key",
)

connector.configure_datasource()


async def main():
    await connector.index_data_async(mode=IndexingMode.FULL)


asyncio.run(main())
```

### Sync Fallback

The async connector provides sync fallback methods that use `asyncio.run()` internally:

- `connector.index_data(mode=IndexingMode.FULL)` — wraps `index_data_async()`
- `connector.get_data()` — collects all async items into a list

These are convenient for scripts that don't need an async event loop, but they block the calling thread and lose the streaming benefit. Prefer `index_data_async()` when possible.
