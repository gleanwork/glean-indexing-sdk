"""High-level connector runners that wrap `mock_glean_client` for one-line tests.

`run_connector` and `run_connector_async` patch the Glean client surface, run
the connector against a recording mock, and return the resulting
:class:`MockGleanClient` for assertions.

The sync runner detects a running asyncio loop and raises a clear error
directing async users to `run_connector_async` — without this guard,
`asyncio.run()` inside `BaseAsyncStreamingDatasourceConnector.index_data`
would fail with `RuntimeError: asyncio.run() cannot be called from a running
event loop`.
"""

import asyncio
from typing import Optional

from glean.indexing.connectors.base_async_streaming_datasource_connector import (
    BaseAsyncStreamingDatasourceConnector,
)
from glean.indexing.connectors.base_connector import BaseConnector
from glean.indexing.models import ConnectorOptions, IndexingMode
from glean.indexing.testing.mock_client import MockGleanClient, mock_glean_client


def _running_loop() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def run_connector(
    connector: BaseConnector,
    *,
    mode: IndexingMode = IndexingMode.FULL,
    options: Optional[ConnectorOptions] = None,
) -> MockGleanClient:
    """Run a connector against a recording mock and return the captured client.

    Args:
        connector: Any connector subclass (datasource, streaming, async-streaming, people).
        mode: The indexing mode to pass through to `connector.index_data`.
        options: Optional `ConnectorOptions` forwarded to `connector.index_data`.

    Returns:
        The :class:`MockGleanClient` that recorded the run. Assert on its
        `documents_posted`, `employees_posted`, etc., or use the matching
        `assert_*` methods.

    Raises:
        TypeError: If `connector` is not a `BaseConnector` instance.
        RuntimeError: If called from inside a running asyncio loop with an
            async-streaming connector. Use :func:`run_connector_async` instead.
    """
    if not isinstance(connector, BaseConnector):
        raise TypeError(
            f"run_connector expected a BaseConnector instance, got {type(connector).__name__}"
        )

    if isinstance(connector, BaseAsyncStreamingDatasourceConnector) and _running_loop():
        raise RuntimeError(
            "run_connector() cannot drive an async streaming connector from inside a "
            "running event loop. Use `await run_connector_async(connector)` instead."
        )

    with mock_glean_client() as client:
        connector.index_data(mode=mode, options=options)
    return client


async def run_connector_async(
    connector: BaseConnector,
    *,
    mode: IndexingMode = IndexingMode.FULL,
    options: Optional[ConnectorOptions] = None,
) -> MockGleanClient:
    """Async variant of :func:`run_connector`.

    For `BaseAsyncStreamingDatasourceConnector` instances, awaits
    `index_data_async` directly (no nested `asyncio.run`). For sync
    connectors, calls `index_data` inline — useful when a test is already
    running under `pytest-asyncio` and wants to drive a sync connector
    without dropping into a sync test function.

    Args:
        connector: Any connector subclass.
        mode: The indexing mode to pass through.
        options: Optional `ConnectorOptions` forwarded to the connector.

    Returns:
        The :class:`MockGleanClient` that recorded the run.

    Raises:
        TypeError: If `connector` is not a `BaseConnector` instance.
    """
    if not isinstance(connector, BaseConnector):
        raise TypeError(
            f"run_connector_async expected a BaseConnector instance, got {type(connector).__name__}"
        )

    with mock_glean_client() as client:
        if isinstance(connector, BaseAsyncStreamingDatasourceConnector):
            await connector.index_data_async(mode=mode, options=options)
        else:
            connector.index_data(mode=mode, options=options)
    return client
