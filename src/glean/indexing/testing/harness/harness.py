"""``TestHarness`` — progressive connector testing across three phases.

Phase 1 (full mock):
    Delegates to the existing :func:`~glean.indexing.testing.run_connector` /
    :func:`~glean.indexing.testing.run_connector_async` helpers.  The Glean
    API is fully mocked; the connector's own data clients are not touched, so
    use :class:`~glean.indexing.testing.StaticDataClient` (or similar) to
    avoid real network calls on the source side.

Phase 2 (integration — real source, mock Glean, local cache):
    Wraps each connector data client with a ``Recording*`` or ``Replay*``
    wrapper depending on whether a valid cache fixture already exists.
    Push side is mocked; pull side hits the real API on first run and replays
    from NDJSON on subsequent runs.

Phase 3 (end-to-end — real source, real Glean):
    Calls ``connector.index_data()`` without any mock patching.  Requires
    ``GLEAN_SERVER_URL`` / ``GLEAN_INDEXING_API_TOKEN`` environment variables,
    and uploads real documents with no automated cleanup. It never reads or
    writes Phase 2 integration fixtures. Pass ``confirm=True`` only after
    verifying the target is a dedicated test instance, not production.
    Per-client ``max_items`` from ``TestConfig`` are applied before the run.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import contextmanager
from itertools import islice
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Generator, Optional, Sequence, Union

from glean.indexing.connectors.base_async_streaming_data_client import BaseAsyncStreamingDataClient
from glean.indexing.connectors.base_connector import BaseConnector
from glean.indexing.connectors.base_data_client import BaseDataClient
from glean.indexing.connectors.base_streaming_data_client import BaseStreamingDataClient
from glean.indexing.exceptions import LiveEndToEndNotConfirmedError
from glean.indexing.models import ConnectorOptions, IndexingMode
from glean.indexing.push.status import IndexingWaitResult, document_status_requests
from glean.indexing.testing.harness.cache.manifest import CacheManifest
from glean.indexing.testing.harness.cache.recording_client import (
    RecordingAsyncStreamingClientWrapper,
    RecordingDataClientWrapper,
    RecordingStreamingClientWrapper,
)
from glean.indexing.testing.harness.cache.replay_client import (
    ReplayAsyncStreamingClientWrapper,
    ReplayDataClientWrapper,
    ReplayStreamingClientWrapper,
)
from glean.indexing.testing.harness.config import ClientConfig, TestConfig
from glean.indexing.testing.harness.indexing_wait import (
    capture_document_uploads,
    wait_for_documents_to_index,
)
from glean.indexing.testing.harness.permissions import assert_negative_identities_absent
from glean.indexing.testing.mock_client import MockGleanClient
from glean.indexing.testing.runner import run_connector, run_connector_async

logger = logging.getLogger(__name__)

AnyDataClient = Union[
    BaseDataClient[Any],
    BaseStreamingDataClient[Any],
    BaseAsyncStreamingDataClient[Any],
]

_MANIFEST_FILENAME = "manifest.json"


class _LiveDataClient(BaseDataClient[Any]):
    """Apply a live-run limit without reading or writing integration fixtures."""

    def __init__(self, inner: BaseDataClient[Any], max_items: Optional[int]) -> None:
        self._inner = inner
        self._max_items = max_items

    def get_source_data(self, **kwargs: Any) -> Sequence[Any]:
        items = list(self._inner.get_source_data(**kwargs))
        return items if self._max_items is None else items[: self._max_items]


class _LiveStreamingDataClient(BaseStreamingDataClient[Any]):
    """Streaming live-run limit that reads directly from the source client."""

    def __init__(self, inner: BaseStreamingDataClient[Any], max_items: Optional[int]) -> None:
        self._inner = inner
        self._max_items = max_items

    def get_source_data(self, **kwargs: Any) -> Generator[Any, None, None]:
        items = self._inner.get_source_data(**kwargs)
        yield from items if self._max_items is None else islice(items, self._max_items)


class _LiveAsyncStreamingDataClient(BaseAsyncStreamingDataClient[Any]):
    """Async live-run limit that reads directly from the source client."""

    def __init__(self, inner: BaseAsyncStreamingDataClient[Any], max_items: Optional[int]) -> None:
        self._inner = inner
        self._max_items = max_items

    async def get_source_data(self, **kwargs: Any) -> AsyncGenerator[Any, None]:
        items = self._inner.get_source_data(**kwargs)
        if self._max_items is None:
            async for item in items:
                yield item
            return
        for _ in range(self._max_items):
            try:
                yield await anext(items)
            except StopAsyncIteration:
                return


def _sdk_version() -> str:
    try:
        from importlib.metadata import version

        return version("glean-indexing-sdk")
    except Exception:
        return "unknown"


def _resolve_glean_target() -> str:
    """Best-effort display string for the configured Glean target.

    Read directly from the environment rather than via
    :func:`~glean.indexing.common.glean_client.api_client` so the target can
    be surfaced in the confirmation guard even when it (or the API token) is
    unset -- that is itself the misconfiguration this guard exists to catch.
    """
    return (
        os.getenv("GLEAN_SERVER_URL") or os.getenv("GLEAN_INSTANCE") or "<GLEAN_SERVER_URL not set>"
    )


def _log_cleanup_instructions(datasource: str, documents: Sequence[Any]) -> None:
    """Log a copy-pasteable command to remove every document this run uploaded.

    Live end-to-end runs have no automated cleanup, so the operator's only
    path back to a clean datasource is deleting what was just uploaded.
    """
    requests = document_status_requests(documents)
    if not requests:
        return
    document_flags = " ".join(f"--document {req.object_type} {req.doc_id}" for req in requests)
    logger.warning(
        "Live end-to-end run uploaded %d document(s) to datasource %r. These are "
        "NOT cleaned up automatically. To remove them: "
        "glean-idx document delete --datasource %s %s",
        len(requests),
        datasource,
        datasource,
        document_flags,
    )


def _should_use_cache(
    manifest_path: Path,
    use_cache: bool,
    refresh_cache: bool,
) -> bool:
    """Return ``True`` if a valid, non-stale cache fixture should be replayed."""
    if not use_cache or refresh_cache:
        return False
    if not manifest_path.exists():
        return False
    # Also require the data file to exist; a manifest without data is a partial write.
    data_path = manifest_path.parent / "data.ndjson"
    if not data_path.exists():
        return False
    try:
        manifest = CacheManifest.load(manifest_path)
    except Exception:
        return False
    return not manifest.is_stale(_sdk_version())


def _wrap_live_client(client: AnyDataClient, max_items: Optional[int]) -> AnyDataClient:
    """Limit a real source client without consulting integration fixtures."""
    if isinstance(client, BaseAsyncStreamingDataClient):
        return _LiveAsyncStreamingDataClient(client, max_items)
    if isinstance(client, BaseStreamingDataClient):
        return _LiveStreamingDataClient(client, max_items)
    return _LiveDataClient(client, max_items)


def _wrap_client(
    attr_name: str,
    client: AnyDataClient,
    *,
    cache_dir: Path,
    connector_name: str,
    use_cache: bool,
    refresh_cache: bool,
    max_items: Optional[int],
) -> AnyDataClient:
    """Return a recording or replay wrapper for *client*."""
    manifest_path = cache_dir / connector_name / "integration" / attr_name / _MANIFEST_FILENAME
    if _should_use_cache(manifest_path, use_cache=use_cache, refresh_cache=refresh_cache):
        logger.debug("Cache HIT for client '%s'", attr_name)
        if isinstance(client, BaseAsyncStreamingDataClient):
            return ReplayAsyncStreamingClientWrapper(
                cache_dir=cache_dir,
                connector_name=connector_name,
                client_name=attr_name,
                max_items=max_items,
            )
        if isinstance(client, BaseStreamingDataClient):
            return ReplayStreamingClientWrapper(
                cache_dir=cache_dir,
                connector_name=connector_name,
                client_name=attr_name,
                max_items=max_items,
            )
        return ReplayDataClientWrapper(
            cache_dir=cache_dir,
            connector_name=connector_name,
            client_name=attr_name,
            max_items=max_items,
        )

    logger.debug("Cache MISS for client '%s' — recording", attr_name)
    if isinstance(client, BaseAsyncStreamingDataClient):
        return RecordingAsyncStreamingClientWrapper(
            inner=client,
            cache_dir=cache_dir,
            connector_name=connector_name,
            client_name=attr_name,
            max_items=max_items,
        )
    if isinstance(client, BaseStreamingDataClient):
        return RecordingStreamingClientWrapper(
            inner=client,
            cache_dir=cache_dir,
            connector_name=connector_name,
            client_name=attr_name,
            max_items=max_items,
        )
    return RecordingDataClientWrapper(
        inner=client,
        cache_dir=cache_dir,
        connector_name=connector_name,
        client_name=attr_name,
        max_items=max_items,
    )


@contextmanager
def _patched_clients(
    connector: BaseConnector,
    clients: Dict[str, AnyDataClient],
    config: TestConfig,
    *,
    use_integration_fixtures: bool = True,
) -> Generator[None, None, None]:
    """Context manager that monkey-patches connector client attributes.

    Replaces each ``connector.<attr_name>`` with a recording or replay wrapper
    for the duration of the block, then restores the originals.

    Raises:
        AttributeError: If a key in *clients* does not correspond to an
            attribute on the connector.
    """
    cache_dir = Path(config.cache_dir)
    connector_name = connector.name  # type: ignore[attr-defined]
    originals: Dict[str, AnyDataClient] = {}

    try:
        for attr_name, client in clients.items():
            if not hasattr(connector, attr_name):
                raise AttributeError(
                    f"Connector {type(connector).__name__!r} has no attribute {attr_name!r}. "
                    f"Verify the 'clients' dict keys match the connector's data-client attribute names."
                )
            originals[attr_name] = getattr(connector, attr_name)

            client_cfg = config.clients.get(attr_name, ClientConfig())
            max_items = client_cfg.max_items

            wrapped = (
                _wrap_client(
                    attr_name,
                    client,
                    cache_dir=cache_dir,
                    connector_name=connector_name,
                    use_cache=config.use_cache,
                    refresh_cache=config.refresh_cache,
                    max_items=max_items,
                )
                if use_integration_fixtures
                else _wrap_live_client(client, max_items)
            )
            setattr(connector, attr_name, wrapped)

        yield
    finally:
        for attr_name, original in originals.items():
            setattr(connector, attr_name, original)


class TestHarness:
    """Progressive connector testing harness.

    Wraps a connector and a :class:`~glean.indexing.testing.harness.config.TestConfig`
    to provide three levels of test fidelity without duplicating mock infrastructure.

    Args:
        connector: Any ``BaseConnector`` subclass (datasource, streaming, async-streaming, people).
        config: Harness configuration.  Defaults to an in-process ``TestConfig()`` if not given.
        clients: Mapping of *connector attribute name* → data-client instance.  Keys must
            match attributes on the connector (e.g. ``"data_client"``, ``"tickets_client"``).
            Required for Phase 2 (integration) to enable recording/replay.  Not needed for Phase 1.

    Example — Phase 1::

        harness = TestHarness(
            connector=MyConnector(data_client=StaticDataClient([...])),
            config=TestConfig(),
        )
        client = harness.run_full_mock()
        client.assert_documents_posted(5)

    Example — Phase 2::

        harness = TestHarness(
            connector=my_connector,
            config=TestConfig.from_yaml("testing_config.yaml"),
            clients={"data_client": real_tickets_client},
        )
        client = harness.run_integration_test()
        client.assert_documents_posted()
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

        On the first call (cache miss) each data client in ``self._clients``
        is wrapped with a recording wrapper that forwards calls to the real
        API and writes items to NDJSON.  On subsequent calls (cache hit) items
        are replayed from disk without touching the real API.

        Pass ``config.refresh_cache=True`` to force re-recording.

        Args:
            mode: Indexing mode forwarded to ``connector.index_data``.
            options: Optional :class:`~glean.indexing.models.ConnectorOptions`.

        Returns:
            A :class:`~glean.indexing.testing.mock_client.MockGleanClient`.

        Raises:
            AttributeError: If a key in ``clients`` does not correspond to a
                connector attribute.
        """
        with _patched_clients(self._connector, self._clients, self._config):
            result = run_connector(self._connector, mode=mode, options=options)

        if self._config.negative_test_identities:
            assert_negative_identities_absent(
                result.documents_posted, self._config.negative_test_identities
            )

        return result

    async def run_integration_test_async(
        self,
        *,
        mode: IndexingMode = IndexingMode.FULL,
        options: Optional[ConnectorOptions] = None,
    ) -> MockGleanClient:
        """Async variant of :meth:`run_integration_test`.

        Args:
            mode: Indexing mode forwarded to ``connector.index_data_async``.
            options: Optional :class:`~glean.indexing.models.ConnectorOptions`.

        Returns:
            A :class:`~glean.indexing.testing.mock_client.MockGleanClient`.
        """
        with _patched_clients(self._connector, self._clients, self._config):
            result = await run_connector_async(self._connector, mode=mode, options=options)

        if self._config.negative_test_identities:
            assert_negative_identities_absent(
                result.documents_posted, self._config.negative_test_identities
            )

        return result

    # ------------------------------------------------------------------
    # Phase 3 — end-to-end (real source, real Glean)
    # ------------------------------------------------------------------

    def run_end_to_end(
        self,
        *,
        mode: IndexingMode = IndexingMode.FULL,
        options: Optional[ConnectorOptions] = None,
        confirm: bool = False,
    ) -> IndexingWaitResult | None:
        """Run the connector against the real source and real Glean.

        The Glean API is **not** mocked — this exercises the full indexing
        path and uploads real documents with **no automated cleanup**.
        Connector clients registered via the ``clients`` constructor argument
        are temporarily wrapped to enforce per-client ``max_items`` limits while
        still calling the current source. Live runs do not read or write the
        integration phase's recorded fixtures. Clients not passed in ``clients``
        are left untouched.

        The Glean client is configured from environment variables:

        - ``GLEAN_SERVER_URL`` (preferred) or ``GLEAN_INSTANCE`` (deprecated)
        - ``GLEAN_INDEXING_API_TOKEN``

        The :attr:`~TestConfig.run_id_prefix` from config is logged but not
        used to namespace the datasource (the connector's own datasource name
        is used as-is).

        **Production safety:** this method refuses to run unless ``confirm``
        is ``True``, since a misconfigured ``GLEAN_SERVER_URL`` would upload
        test data to a real instance with nothing to catch the mistake and no
        automated way to remove it afterward. Before passing ``confirm=True``,
        verify the resolved target is a dedicated test instance, not
        production. On success, the identifiers of every uploaded document are
        logged together with the ``glean-idx document delete`` command that
        removes them, since that is the only cleanup path available.

        Args:
            mode: Indexing mode forwarded to ``connector.index_data``.
            options: Optional :class:`~glean.indexing.models.ConnectorOptions`.
            confirm: Must be explicitly set to ``True`` to run this phase.

        Returns:
            The document indexing outcome, or ``None`` when no documents were uploaded.

        Raises:
            ~glean.indexing.exceptions.LiveEndToEndNotConfirmedError: If
                ``confirm`` is not ``True``.
            ~glean.indexing.exceptions.MissingEnvironmentVariableError: If
                ``GLEAN_INDEXING_API_TOKEN`` or the server URL is missing from
                the environment.
        """
        target = _resolve_glean_target()
        if not confirm:
            raise LiveEndToEndNotConfirmedError(target)

        logger.warning(
            "Running LIVE end-to-end test for connector %r against %s. This "
            "uploads real documents with no automated cleanup -- make sure "
            "this is a dedicated test instance, not production.",
            self._connector.name,  # type: ignore[attr-defined]
            target,
        )
        logger.info(
            "Starting end-to-end run (run_id_prefix=%r, mode=%s)",
            self._config.run_id_prefix,
            mode.name,
        )
        with capture_document_uploads() as uploaded_documents:
            with _patched_clients(
                self._connector,
                self._clients,
                self._config,
                use_integration_fixtures=False,
            ):
                self._connector.index_data(mode=mode, options=options)  # type: ignore[attr-defined]

        _log_cleanup_instructions(self._connector.name, uploaded_documents)  # type: ignore[attr-defined]

        return wait_for_documents_to_index(
            self._connector.name,  # type: ignore[attr-defined]
            uploaded_documents,
        )

    async def run_end_to_end_async(
        self,
        *,
        mode: IndexingMode = IndexingMode.FULL,
        options: Optional[ConnectorOptions] = None,
        confirm: bool = False,
    ) -> IndexingWaitResult | None:
        """Async variant of :meth:`run_end_to_end`.

        For :class:`~glean.indexing.connectors.BaseAsyncStreamingDatasourceConnector`
        subclasses this calls ``connector.index_data_async()``; for sync
        connectors it falls back to ``connector.index_data()``.

        Like the sync variant, connector clients registered via ``clients``
        are temporarily wrapped to enforce ``max_items``; the Glean API itself
        is not mocked, real documents are uploaded with no automated cleanup,
        and this method refuses to run unless ``confirm=True``.

        Args:
            mode: Indexing mode forwarded to the connector.
            options: Optional :class:`~glean.indexing.models.ConnectorOptions`.
            confirm: Must be explicitly set to ``True`` to run this phase.

        Returns:
            The document indexing outcome, or ``None`` when no documents were uploaded.

        Raises:
            ~glean.indexing.exceptions.LiveEndToEndNotConfirmedError: If
                ``confirm`` is not ``True``.
            ~glean.indexing.exceptions.MissingEnvironmentVariableError: If
                environment variables for the Glean client are missing.
        """
        from glean.indexing.connectors.base_async_streaming_datasource_connector import (
            BaseAsyncStreamingDatasourceConnector,
        )

        target = _resolve_glean_target()
        if not confirm:
            raise LiveEndToEndNotConfirmedError(target)

        logger.warning(
            "Running LIVE end-to-end test for connector %r against %s. This "
            "uploads real documents with no automated cleanup -- make sure "
            "this is a dedicated test instance, not production.",
            self._connector.name,  # type: ignore[attr-defined]
            target,
        )
        logger.info(
            "Starting async end-to-end run (run_id_prefix=%r, mode=%s)",
            self._config.run_id_prefix,
            mode.name,
        )
        with capture_document_uploads() as uploaded_documents:
            with _patched_clients(
                self._connector,
                self._clients,
                self._config,
                use_integration_fixtures=False,
            ):
                if isinstance(self._connector, BaseAsyncStreamingDatasourceConnector):
                    await self._connector.index_data_async(mode=mode, options=options)
                else:
                    self._connector.index_data(mode=mode, options=options)  # type: ignore[attr-defined]

        _log_cleanup_instructions(self._connector.name, uploaded_documents)  # type: ignore[attr-defined]

        return await asyncio.to_thread(
            wait_for_documents_to_index,
            self._connector.name,  # type: ignore[attr-defined]
            uploaded_documents,
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
