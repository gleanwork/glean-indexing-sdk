"""HTTP-based streaming data client helpers for pull recipes."""

import time
from collections.abc import Callable, Mapping
from typing import Generic

import httpx

from glean.indexing.connectors.base_streaming_data_client import BaseStreamingDataClient
from glean.indexing.models import TSourceData
from recipes.pull.http_client import PullHttpClient
from recipes.pull.options import PullOptions


class BasePullHttpStreamingDataClient(BaseStreamingDataClient[TSourceData], Generic[TSourceData]):
    """Base class for streaming data clients backed by `PullHttpClient`.

    Subclasses still own source-specific extraction in `get_source_data`, but can use
    `self.http` for retries, response parsing, and pagination.
    """

    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str] | None = None,
        options: PullOptions | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Initialize the shared pull HTTP client."""
        self.http = PullHttpClient(
            base_url=base_url,
            headers=headers,
            options=options,
            client=client,
            sleep=sleep,
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self.http.close()
