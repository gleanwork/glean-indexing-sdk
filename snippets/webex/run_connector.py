"""Run the Webex connector snippet.

Required env vars:
    WEBEX_ACCESS_TOKEN
    GLEAN_SERVER_URL or GLEAN_INSTANCE
    GLEAN_INDEXING_API_TOKEN

Optional env vars:
    WEBEX_DATASOURCE_NAME
    WEBEX_LAST_ACTIVITY_CURSOR
"""

import os

from glean.indexing.models import IndexingMode
from glean.indexing.pull import (
    BearerTokenAuth,
    PullHttpClient,
    PullOptions,
    PullRetryOptions,
    RateLimitConfig,
)

from snippets.webex.client import WEBEX_API_BASE_URL, WebexClient
from snippets.webex.connector import WebexConnector
from snippets.webex.data_client import WebexDataClient


def build_connector() -> WebexConnector:
    """Build a Webex connector from environment variables."""
    token = os.environ["WEBEX_ACCESS_TOKEN"]
    http_client = PullHttpClient(
        base_url=WEBEX_API_BASE_URL,
        auth=BearerTokenAuth(token),
        options=PullOptions(
            timeout_seconds=30,
            retries=PullRetryOptions(max_attempts=5),
            mask_logs=True,
        ),
        rate_limiter=RateLimitConfig(calls=300, period_seconds=60).create_limiter(),
    )
    datasource_name = os.getenv("WEBEX_DATASOURCE_NAME", "webex")
    return WebexConnector(datasource_name, WebexDataClient(WebexClient(http_client)))


if __name__ == "__main__":
    mode = IndexingMode(os.getenv("WEBEX_INDEXING_MODE", IndexingMode.FULL.value))
    connector = build_connector()
    connector.configure_datasource()
    connector.index_data(mode=mode)
