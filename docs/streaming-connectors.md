# Streaming Connectors

Streaming connectors fetch, transform, and upload one batch at a time. Use them for large or
paginated sources where loading the complete dataset into memory is impractical.

Streaming controls memory usage; it does not change crawl scope. A full crawl must still exhaust
every in-scope page before completing. If any page fails, raise the error rather than returning a
partial result, because a successful partial full crawl can delete omitted documents as stale.

> **Important:** Do not set a production full crawl's `max_items` to a sample limit. Also note that
> an empty stream currently makes no upload call, so it does not remove documents left by an earlier
> crawl.

## Synchronous streaming

Use `BaseStreamingDatasourceConnector` when the source client is synchronous. For common HTTP APIs,
`BasePullHttpStreamingDataClient` supplies retries, response parsing, optional rate limiting, and
link, offset, or cursor pagination.

### 1. Define the source data

```python snippet=streaming/article_data.py
from typing import TypedDict


class ArticleData(TypedDict):
    """Knowledge base article returned by the source API."""

    id: str
    title: str
    content: str
    author: str
    allowed_users: list[str]
    updated_at: str
    url: str
```

### 2. Configure the pull recipe

This example expects the source to return a top-level JSON list and accept `limit` and `offset`
parameters. It remaps the SDK's `since` argument to the source's `modified_since` parameter.

```python snippet=streaming/article_data_client.py
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
```

Leave `max_items=None` for a complete crawl. Choose the pagination mode and parameter names that
match the source API. Offset pagination requires stable ordering or a source snapshot; prefer a
cursor when the collection can change during a crawl. Configure a `TokenBucketRateLimiter` when the
source publishes a request quota.

### 3. Transform each batch

`transform()` still receives a `Sequence`; the connector collects at most `batch_size` source items
before calling it.

```python snippet=streaming/article_connector.py
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
        name="knowledge_base",
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
```

### 4. Run the full crawl

Place the four files in the same Python package so their relative imports resolve.

```python snippet=streaming/run_connector.py
import os

from glean.indexing.models import IndexingMode

from .article_connector import KnowledgeBaseConnector
from .article_data_client import LargeKnowledgeBaseClient

data_client = LargeKnowledgeBaseClient(
    kb_api_url="https://kb-api.company.com",
    api_key=os.environ["SOURCE_API_TOKEN"],
)
connector = KnowledgeBaseConnector(
    name="knowledge_base",
    data_client=data_client,
)

connector.configure_datasource()
connector.index_data(mode=IndexingMode.FULL)
```

## Asynchronous streaming

Use `BaseAsyncStreamingDatasourceConnector` when the source has a genuinely asynchronous client.
The SDK does not currently provide an async counterpart to `PullHttpClient`, so the source client
must implement its own timeout, retry, and rate-limit policy. This example focuses on pagination
and streaming with `httpx.AsyncClient`. It expects every page to contain an `events` list and an
explicit `next_page` value; a missing field is treated as an incomplete response.

### 1. Define the source data

```python snippet=async_streaming/event_data.py
from typing import TypedDict


class EventData(TypedDict):
    """Event returned by the source API."""

    id: str
    title: str
    description: str
    organizer: str
    allowed_users: list[str]
    event_url: str
    updated_at: str
```

### 2. Stream source pages asynchronously

```python snippet=async_streaming/event_data_client.py
import asyncio
from collections.abc import AsyncGenerator
from typing import Any, cast

import httpx

from glean.indexing.connectors import BaseAsyncStreamingDataClient

from .event_data import EventData


class EventDataClient(BaseAsyncStreamingDataClient[EventData]):
    """Streams every event from an async paginated source API."""

    _RETRY_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(self, api_url: str, api_key: str, max_attempts: int = 3) -> None:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.max_attempts = max_attempts

    async def get_source_data(self, **kwargs: Any) -> AsyncGenerator[EventData, None]:
        """Yield all event pages, retrying transient source failures."""
        page = 1
        page_size = 100
        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                params: dict[str, Any] = {"page": page, "size": page_size}
                if since := kwargs.get("since"):
                    params["modified_since"] = since

                response = await self._get_page(client, headers, params)
                payload = response.json()
                if (
                    not isinstance(payload, dict)
                    or "events" not in payload
                    or "next_page" not in payload
                ):
                    raise TypeError("Expected an object containing `events` and `next_page` fields")
                events = payload["events"]
                if not isinstance(events, list):
                    raise TypeError("Expected `events` to be a list")

                for event in events:
                    yield cast(EventData, event)

                next_page = payload.get("next_page")
                if next_page is None:
                    return
                if not isinstance(next_page, int) or next_page <= page:
                    raise TypeError("Expected `next_page` to advance to a later integer page")
                page = next_page

    async def _get_page(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        params: dict[str, Any],
    ) -> httpx.Response:
        for attempt in range(1, self.max_attempts + 1):
            response: httpx.Response | None = None
            try:
                response = await client.get(
                    f"{self.api_url}/events",
                    headers=headers,
                    params=params,
                )
                if response.status_code not in self._RETRY_STATUS_CODES:
                    response.raise_for_status()
                    return response
                if attempt == self.max_attempts:
                    response.raise_for_status()
            except httpx.RequestError:
                if attempt == self.max_attempts:
                    raise

            retry_after = response.headers.get("Retry-After") if response else None
            try:
                delay = max(0.0, float(retry_after)) if retry_after else 2 ** (attempt - 1)
            except ValueError:
                delay = 2 ** (attempt - 1)
            await asyncio.sleep(min(delay, 30.0))

        raise RuntimeError("Unreachable retry state")
```

### 3. Transform each batch

```python snippet=async_streaming/event_connector.py
from datetime import datetime
from typing import Sequence

from glean.api_client.models import DocumentPermissionsDefinition
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
    """Transforms asynchronously streamed events into Glean documents."""

    configuration = CustomDatasourceConfig(
        name="company_events",
        display_name="Company Events",
        url_regex=r"https://events\.company\.com/.*",
        is_user_referenced_by_email=True,
    )

    def __init__(self, name: str, api_url: str, api_key: str) -> None:
        super().__init__(
            name,
            EventDataClient(api_url=api_url, api_key=api_key),
        )
        self.batch_size = 50

    def transform(self, data: Sequence[EventData]) -> Sequence[DocumentDefinition]:
        return [
            DocumentDefinition(
                id=event["id"],
                title=event["title"],
                datasource=self.name,
                view_url=event["event_url"],
                body=ContentDefinition(
                    mime_type="text/plain",
                    text_content=event["description"],
                ),
                author=UserReferenceDefinition(email=event["organizer"]),
                permissions=DocumentPermissionsDefinition(
                    allowed_users=[
                        UserReferenceDefinition(email=email) for email in event["allowed_users"]
                    ]
                ),
                updated_at=int(
                    datetime.fromisoformat(event["updated_at"].replace("Z", "+00:00")).timestamp()
                ),
            )
            for event in data
        ]
```

### 4. Run from an async entry point

Place the four files in the same Python package so their relative imports resolve.

```python snippet=async_streaming/run_connector.py
import asyncio
import os

from glean.indexing.models import IndexingMode

from .event_connector import EventConnector

connector = EventConnector(
    name="company_events",
    api_url="https://events-api.company.com",
    api_key=os.environ["SOURCE_API_TOKEN"],
)
connector.configure_datasource()


async def main() -> None:
    await connector.index_data_async(mode=IndexingMode.FULL)


asyncio.run(main())
```

Prefer `await connector.index_data_async(...)` and `connector.get_data_async(...)` in asynchronous
applications. The synchronous fallbacks call `asyncio.run()`, which fails inside an existing event
loop. The synchronous `get_data()` fallback also materializes the entire stream into a list and
therefore loses the memory benefit of streaming.

## Permissions and options

Streaming connector implementations do not run `get_identities()` before uploading documents. If
the documents reference datasource users or groups, index that identity graph separately.

The examples map per-document user ACLs from the source response. Do not replace them with an
allow-all default unless the source content is intentionally visible to every user.

`ConnectorOptions` controls force restart, synchronous stale deletion, upload timeout, and
concurrent middle-page uploads. See [Advanced Usage](advanced.md) for the current option behavior
and limitations.
