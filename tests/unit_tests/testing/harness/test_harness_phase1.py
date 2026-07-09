"""Tests for TestHarness Phase 1 — full mock mode."""

import pytest

from glean.indexing.models import ConnectorOptions, IndexingMode
from glean.indexing.testing import (
    StaticAsyncStreamingDataClient,
    StaticDataClient,
    StaticStreamingDataClient,
)
from glean.indexing.testing.harness import TestConfig, TestHarness
from glean.indexing.testing.mock_client import MockGleanClient
from tests.unit_tests.testing._fakes import (
    AsyncStreamingFake,
    DatasourceFake,
    PeopleFake,
    StreamingFake,
)

_DOCS = [{"id": str(i), "title": f"Doc {i}"} for i in range(3)]
_EMPS = [
    {"email": "a@b.com", "first_name": "A", "last_name": "B"},
    {"email": "c@d.com", "first_name": "C", "last_name": "D"},
]


class TestTestHarnessInit:
    def test_accepts_connector(self):
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(_DOCS))
        harness = TestHarness(connector=connector, config=TestConfig())
        assert harness.connector is connector
        assert harness.config.run_id_prefix == "sdk_test"

    def test_default_config(self):
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(_DOCS))
        harness = TestHarness(connector=connector)
        assert isinstance(harness.config, TestConfig)

    def test_rejects_non_connector(self):
        with pytest.raises(TypeError, match="BaseConnector"):
            TestHarness(connector="not-a-connector", config=TestConfig())  # type: ignore[arg-type]

    def test_clients_stored(self):
        client = StaticDataClient(_DOCS)
        connector = DatasourceFake(name="ds", data_client=client)
        harness = TestHarness(
            connector=connector,
            config=TestConfig(),
            clients={"data_client": client},
        )
        assert "data_client" in harness.clients


class TestRunFullMock:
    def test_datasource_connector(self):
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(_DOCS))
        harness = TestHarness(connector=connector, config=TestConfig())
        result = harness.run_full_mock()

        assert isinstance(result, MockGleanClient)
        result.assert_documents_posted(count=3, datasource="ds")

    def test_streaming_connector(self):
        connector = StreamingFake(name="ss", data_client=StaticStreamingDataClient(_DOCS))
        harness = TestHarness(connector=connector, config=TestConfig())
        result = harness.run_full_mock()

        result.assert_documents_posted(count=3, datasource="ss")

    def test_people_connector(self):
        connector = PeopleFake(name="p", data_client=StaticDataClient(_EMPS))
        harness = TestHarness(connector=connector, config=TestConfig())
        result = harness.run_full_mock()

        result.assert_employees_posted(count=2)

    def test_incremental_mode_propagates(self):
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(_DOCS[:1]))
        harness = TestHarness(connector=connector, config=TestConfig())
        result = harness.run_full_mock(mode=IndexingMode.INCREMENTAL)

        result.assert_documents_posted(count=1)

    def test_options_propagate(self):
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(_DOCS[:1]))
        harness = TestHarness(connector=connector, config=TestConfig())
        result = harness.run_full_mock(options=ConnectorOptions(force_restart=True))

        call = result.indexing.documents.bulk_index.call_args_list[0]
        assert call.kwargs["force_restart_upload"] is True

    def test_returns_fresh_client_per_run(self):
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(_DOCS))
        harness = TestHarness(connector=connector, config=TestConfig())

        result1 = harness.run_full_mock()
        result2 = harness.run_full_mock()

        # Each run produces an independent MockGleanClient
        assert result1 is not result2
        result1.assert_documents_posted(count=3)
        result2.assert_documents_posted(count=3)


class TestRunFullMockAsync:
    @pytest.mark.asyncio
    async def test_async_streaming_connector(self):
        connector = AsyncStreamingFake(
            name="as",
            async_data_client=StaticAsyncStreamingDataClient(_DOCS),
        )
        harness = TestHarness(connector=connector, config=TestConfig())
        result = await harness.run_full_mock_async()

        assert isinstance(result, MockGleanClient)
        result.assert_documents_posted(count=3, datasource="as")

    @pytest.mark.asyncio
    async def test_sync_connector_works_in_async(self):
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(_DOCS[:2]))
        harness = TestHarness(connector=connector, config=TestConfig())
        result = await harness.run_full_mock_async()

        result.assert_documents_posted(count=2)

    @pytest.mark.asyncio
    async def test_incremental_mode_propagates(self):
        connector = AsyncStreamingFake(
            name="as",
            async_data_client=StaticAsyncStreamingDataClient(_DOCS[:1]),
        )
        harness = TestHarness(connector=connector, config=TestConfig())
        result = await harness.run_full_mock_async(mode=IndexingMode.INCREMENTAL)

        result.assert_documents_posted(count=1)


class TestPhaseStubs:
    def test_run_end_to_end_raises(self):
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(_DOCS))
        harness = TestHarness(connector=connector, config=TestConfig())

        with pytest.raises(NotImplementedError, match="run_end_to_end"):
            harness.run_end_to_end()

    @pytest.mark.asyncio
    async def test_run_end_to_end_async_raises(self):
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(_DOCS))
        harness = TestHarness(connector=connector, config=TestConfig())

        with pytest.raises(NotImplementedError, match="run_end_to_end_async"):
            await harness.run_end_to_end_async()


class TestPublicImport:
    """Verify that TestHarness and TestConfig are importable from the top-level testing package."""

    def test_top_level_import(self):
        from glean.indexing.testing import ClientConfig, TestConfig, TestHarness  # noqa: F401

        assert TestHarness is not None
        assert TestConfig is not None
        assert ClientConfig is not None
