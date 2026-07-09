"""``TestHarness`` — progressive connector testing across three phases.

Phase 1 (full mock):
    Delegates to the existing :func:`~glean.indexing.testing.run_connector` /
    :func:`~glean.indexing.testing.run_connector_async` helpers.  The Glean
    API is fully mocked; the connector's own data clients are not touched, so
    use :class:`~glean.indexing.testing.StaticDataClient` (or similar) to
    avoid real network calls on the source side.

Phase 2 (integration — real source, mock Glean, local cache):
    Not yet implemented.  :meth:`TestHarness.run_integration_test` raises
    ``NotImplementedError`` until PR 2 lands.

Phase 3 (end-to-end — real source, real Glean):
    Not yet implemented.  :meth:`TestHarness.run_end_to_end` raises
    ``NotImplementedError`` until PR 4 lands.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Union

from glean.indexing.connectors.base_async_streaming_data_client import BaseAsyncStreamingDataClient
from glean.indexing.connectors.base_connector import BaseConnector
from glean.indexing.connectors.base_data_client import BaseDataClient
from glean.indexing.connectors.base_streaming_data_client import BaseStreamingDataClient
from glean.indexing.models import ConnectorOptions, IndexingMode
from glean.indexing.testing.harness.config import TestConfig
from glean.indexing.testing.mock_client import MockGleanClient
from glean.indexing.testing.runner import run_connector, run_connector_async

AnyDataClient = Union[
    BaseDataClient[Any],
    BaseStreamingDataClient[Any],
    BaseAsyncStreamingDataClient[Any],
]


class TestHarness:
    """Progressive connector testing harness.

    Wraps a connector and a :class:`~glean.indexing.testing.harness.config.TestConfig`
    to provide three levels of test fidelity without duplicating mock infrastructure.

    Args:
        connector: Any ``BaseConnector`` subclass (datasource, streaming, async-streaming, people).
        config: Harness configuration.  Defaults to an in-process ``TestConfig()`` if not given.
        clients: Mapping of *attribute name* → data-client instance.  Keys must
            correspond to attributes on the connector (e.g. ``"data_client"``,
            ``"tickets_client"``).  Used in Phase 2 (integration) to wrap
            each client with recording / replay logic.  Not required for Phase 1.

    Example::

        harness = TestHarness(
            connector=MyConnector(data_client=StaticDataClient([...])),
            config=TestConfig(),
        )
        client = harness.run_full_mock()
        client.assert_documents_posted(5)
    """

    def __init__(
        self,
        connector: BaseConnector,
        config: Optional[TestConfig] = None,
        clients: Optional[Dict[str, AnyDataClient]] = None,
    ) -> None:
        if not isinstance(connector, BaseConnector):
            raise TypeError(
                f"TestHarness expected a BaseConnector instance, got {type(connector).__name__}"
            )
        self._connector = connector
        self._config = config or TestConfig()
        self._clients: Dict[str, AnyDataClient] = clients or {}

    # ------------------------------------------------------------------
    # Phase 1 — full mock
    # ------------------------------------------------------------------

    def run_full_mock(
        self,
        *,
        mode: IndexingMode = IndexingMode.FULL,
        options: Optional[ConnectorOptions] = None,
    ) -> MockGleanClient:
        """Run the connector against a fully mocked Glean client.

        Delegates to :func:`~glean.indexing.testing.runner.run_connector`.
        The Glean API is fully mocked; no indexing network calls are made.
        The connector's source-side data clients are not replaced, so pass
        :class:`~glean.indexing.testing.StaticDataClient` (or similar) when
        constructing the connector to keep the run fully offline.

        Args:
            mode: Indexing mode forwarded to ``connector.index_data``.
            options: Optional :class:`~glean.indexing.models.ConnectorOptions`.

        Returns:
            A :class:`~glean.indexing.testing.mock_client.MockGleanClient`
            containing the recorded calls.  Assert on ``documents_posted``,
            ``assert_documents_posted``, etc.
        """
        return run_connector(self._connector, mode=mode, options=options)

    async def run_full_mock_async(
        self,
        *,
        mode: IndexingMode = IndexingMode.FULL,
        options: Optional[ConnectorOptions] = None,
    ) -> MockGleanClient:
        """Async variant of :meth:`run_full_mock`.

        Delegates to :func:`~glean.indexing.testing.runner.run_connector_async`.
        Required for ``BaseAsyncStreamingDatasourceConnector`` subclasses when
        already running inside an asyncio event loop.

        Args:
            mode: Indexing mode forwarded to ``connector.index_data_async``.
            options: Optional :class:`~glean.indexing.models.ConnectorOptions`.

        Returns:
            A :class:`~glean.indexing.testing.mock_client.MockGleanClient`.
        """
        return await run_connector_async(self._connector, mode=mode, options=options)

    # ------------------------------------------------------------------
    # Phase 2 — integration test (real source, mock Glean, local cache)
    # ------------------------------------------------------------------

    def run_integration_test(
        self,
        *,
        mode: IndexingMode = IndexingMode.FULL,
        options: Optional[ConnectorOptions] = None,
    ) -> MockGleanClient:
        """Run the connector against the real source with a mocked Glean client.

        Uses a local replay cache to avoid repeated network calls.

        .. note::
            Not yet implemented — will be added in PR 2 (``feature/testing-harness-phase2``).

        Raises:
            NotImplementedError: Always, until PR 2 is merged.
        """
        raise NotImplementedError(
            "run_integration_test is not yet implemented. "
            "It will be available in the feature/testing-harness-phase2 branch."
        )

    async def run_integration_test_async(
        self,
        *,
        mode: IndexingMode = IndexingMode.FULL,
        options: Optional[ConnectorOptions] = None,
    ) -> MockGleanClient:
        """Async variant of :meth:`run_integration_test`.

        Raises:
            NotImplementedError: Always, until PR 2 is merged.
        """
        raise NotImplementedError(
            "run_integration_test_async is not yet implemented. "
            "It will be available in the feature/testing-harness-phase2 branch."
        )

    # ------------------------------------------------------------------
    # Phase 3 — end-to-end (real source, real Glean)
    # ------------------------------------------------------------------

    def run_end_to_end(
        self,
        *,
        mode: IndexingMode = IndexingMode.FULL,
        options: Optional[ConnectorOptions] = None,
    ) -> None:
        """Run the connector against the real source and real Glean.

        Requires ``GLEAN_SERVER_URL`` (or ``GLEAN_INSTANCE``) and
        ``GLEAN_INDEXING_API_TOKEN`` environment variables to be set.

        .. note::
            Not yet implemented — will be added in PR 4 (``feature/testing-harness-phase3``).

        Raises:
            NotImplementedError: Always, until PR 4 is merged.
        """
        raise NotImplementedError(
            "run_end_to_end is not yet implemented. "
            "It will be available in the feature/testing-harness-phase3 branch."
        )

    async def run_end_to_end_async(
        self,
        *,
        mode: IndexingMode = IndexingMode.FULL,
        options: Optional[ConnectorOptions] = None,
    ) -> None:
        """Async variant of :meth:`run_end_to_end`.

        Raises:
            NotImplementedError: Always, until PR 4 is merged.
        """
        raise NotImplementedError(
            "run_end_to_end_async is not yet implemented. "
            "It will be available in the feature/testing-harness-phase3 branch."
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @property
    def config(self) -> TestConfig:
        """The active test configuration."""
        return self._config

    @property
    def connector(self) -> BaseConnector:
        """The connector under test."""
        return self._connector

    @property
    def clients(self) -> Dict[str, AnyDataClient]:
        """The registered data clients, keyed by connector attribute name."""
        return dict(self._clients)
