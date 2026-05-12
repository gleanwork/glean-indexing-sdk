"""Tests for run_connector / run_connector_async."""

import pytest

from glean.indexing.models import ConnectorOptions, IndexingMode
from glean.indexing.testing import (
    StaticAsyncStreamingDataClient,
    StaticDataClient,
    StaticStreamingDataClient,
    run_connector,
    run_connector_async,
)
from tests.unit_tests.testing._fakes import (
    AsyncStreamingFake,
    DatasourceFake,
    PeopleFake,
    StreamingFake,
)

_DOCS = [{"id": str(i), "title": f"Doc {i}"} for i in range(3)]
_EMPS = [
    {"email": "a@b.com", "first_name": "A", "last_name": "B"},
    {"email": "c@b.com", "first_name": "C", "last_name": "D"},
]


class TestRunConnectorSync:
    def test_datasource(self):
        connector = DatasourceFake(name="ds", data_client=StaticDataClient(_DOCS))
        result = run_connector(connector)
        result.assert_documents_posted(count=3, datasource="ds")

    def test_streaming(self):
        connector = StreamingFake(name="ss", data_client=StaticStreamingDataClient(_DOCS))
        result = run_connector(connector)
        result.assert_documents_posted(count=3, datasource="ss")

    def test_async_streaming_via_sync_runner(self):
        connector = AsyncStreamingFake(
            name="as", async_data_client=StaticAsyncStreamingDataClient(_DOCS)
        )
        result = run_connector(connector)
        result.assert_documents_posted(count=3, datasource="as")

    def test_people(self):
        connector = PeopleFake(name="p", data_client=StaticDataClient(_EMPS))
        result = run_connector(connector)
        result.assert_employees_posted(count=2)

    def test_rejects_non_connector(self):
        with pytest.raises(TypeError, match="BaseConnector"):
            run_connector("not-a-connector")  # type: ignore[arg-type]


class TestRunConnectorPropagation:
    def test_mode_propagates(self):
        connector = DatasourceFake(name="m", data_client=StaticDataClient(_DOCS[:1]))
        result = run_connector(connector, mode=IndexingMode.INCREMENTAL)
        result.assert_documents_posted(count=1)

    def test_options_propagate(self):
        connector = DatasourceFake(name="o", data_client=StaticDataClient(_DOCS[:1]))
        result = run_connector(
            connector,
            options=ConnectorOptions(force_restart=True),
        )
        call = result.indexing.documents.bulk_index.call_args_list[0]
        assert call.kwargs["force_restart_upload"] is True


class TestAsyncFootgunGuard:
    @pytest.mark.asyncio
    async def test_run_connector_in_async_context_raises(self):
        connector = AsyncStreamingFake(
            name="as_loop",
            async_data_client=StaticAsyncStreamingDataClient(_DOCS),
        )
        with pytest.raises(RuntimeError, match="run_connector_async"):
            run_connector(connector)


class TestRunConnectorAsync:
    @pytest.mark.asyncio
    async def test_async_streaming(self):
        connector = AsyncStreamingFake(
            name="as",
            async_data_client=StaticAsyncStreamingDataClient(_DOCS),
        )
        result = await run_connector_async(connector)
        result.assert_documents_posted(count=3, datasource="as")

    @pytest.mark.asyncio
    async def test_sync_connector_works(self):
        connector = DatasourceFake(name="ds_async_runner", data_client=StaticDataClient(_DOCS[:2]))
        result = await run_connector_async(connector)
        result.assert_documents_posted(count=2)

    @pytest.mark.asyncio
    async def test_rejects_non_connector(self):
        with pytest.raises(TypeError, match="BaseConnector"):
            await run_connector_async("not-a-connector")  # type: ignore[arg-type]
