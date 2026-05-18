"""Run the Webex connector snippet.

Required env vars:
    WEBEX_ACCESS_TOKEN
    or WEBEX_CLIENT_ID + WEBEX_CLIENT_SECRET + WEBEX_REFRESH_TOKEN
    GLEAN_SERVER_URL or GLEAN_INSTANCE
    GLEAN_INDEXING_API_TOKEN

Optional env vars:
    WEBEX_DATASOURCE_NAME
    WEBEX_CHECKPOINT_PATH
    WEBEX_LAST_ACTIVITY_CURSOR (fallback when WEBEX_CHECKPOINT_PATH is not set)
"""

import os
from pathlib import Path

from glean.indexing.models import IndexingMode
from glean.indexing.pull import (
    BearerTokenAuth,
    PullHttpClient,
    PullOptions,
    PullRetryOptions,
    RateLimitConfig,
)

from snippets.webex.client import WEBEX_API_BASE_URL, WebexClient, WebexOAuthTokenManager
from snippets.webex.checkpoint import FileCheckpointStore
from snippets.webex.connector import WebexConnector
from snippets.webex.data_client import WebexDataClient


def build_connector() -> WebexConnector:
    """Build a Webex connector from environment variables."""
    auth = _auth_from_env()
    http_client = PullHttpClient(
        base_url=WEBEX_API_BASE_URL,
        auth=auth,
        options=PullOptions(
            timeout_seconds=30,
            retries=PullRetryOptions(max_attempts=5),
            mask_logs=True,
        ),
        rate_limiter=RateLimitConfig(calls=300, period_seconds=60).create_limiter(),
    )
    datasource_name = os.getenv("WEBEX_DATASOURCE_NAME", "webex")
    checkpoint_store = _checkpoint_store_from_env()
    return WebexConnector(
        datasource_name,
        WebexDataClient(WebexClient(http_client)),
        checkpoint_store=checkpoint_store,
    )


def _auth_from_env():
    token = os.getenv("WEBEX_ACCESS_TOKEN") or os.getenv("ACCESS_TOKEN")
    if _has_oauth_env():
        token_client = PullHttpClient(
            base_url=WEBEX_API_BASE_URL,
            options=PullOptions(
                timeout_seconds=30,
                retries=PullRetryOptions(max_attempts=5),
                mask_logs=True,
            ),
        )
        return WebexOAuthTokenManager(
            client_id=os.environ["WEBEX_CLIENT_ID"],
            client_secret=os.environ["WEBEX_CLIENT_SECRET"],
            refresh_token=os.environ["WEBEX_REFRESH_TOKEN"],
            access_token=token,
            token_client=token_client,
        )
    if token:
        return BearerTokenAuth(token)
    raise ValueError(
        "Set WEBEX_ACCESS_TOKEN for PAT auth, or WEBEX_CLIENT_ID + WEBEX_CLIENT_SECRET + WEBEX_REFRESH_TOKEN for OAuth"
    )


def _has_oauth_env() -> bool:
    return all(
        [
            os.getenv("WEBEX_CLIENT_ID"),
            os.getenv("WEBEX_CLIENT_SECRET"),
            os.getenv("WEBEX_REFRESH_TOKEN"),
        ]
    )


def _checkpoint_store_from_env() -> FileCheckpointStore | None:
    checkpoint_path = os.getenv("WEBEX_CHECKPOINT_PATH")
    if not checkpoint_path:
        return None
    return FileCheckpointStore(Path(checkpoint_path))


if __name__ == "__main__":
    mode = IndexingMode(os.getenv("WEBEX_INDEXING_MODE", IndexingMode.FULL.value))
    connector = build_connector()
    connector.configure_datasource()
    connector.index_data(mode=mode)
