"""Testing utilities for Glean connectors.

The public surface here is split into two patterns:

- High-level one-liner runners (`run_connector`, `run_connector_async`) plus
  ready-made data clients (`StaticDataClient` and friends) for the common
  case of "feed fake records into my connector and assert on the output."
- Lower-level patch helpers (`mock_glean_client`, `with_mock_glean_client`)
  that yield a recording :class:`MockGleanClient` for tests that want to
  drive `connector.index_data()` themselves.
"""

from glean.indexing.testing.data_clients import (
    StaticAsyncStreamingDataClient,
    StaticDataClient,
    StaticStreamingDataClient,
)
from glean.indexing.testing.mock_client import (
    MockGleanClient,
    mock_glean_client,
    with_mock_glean_client,
)
from glean.indexing.testing.mock_data_source import MockDataSource
from glean.indexing.testing.runner import run_connector, run_connector_async

__all__ = [
    "MockDataSource",
    "MockGleanClient",
    "StaticAsyncStreamingDataClient",
    "StaticDataClient",
    "StaticStreamingDataClient",
    "mock_glean_client",
    "run_connector",
    "run_connector_async",
    "with_mock_glean_client",
]
