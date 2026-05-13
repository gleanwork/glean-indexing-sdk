"""Tests for the StaticDataClient family."""

import pytest

from glean.indexing.testing import (
    StaticAsyncStreamingDataClient,
    StaticDataClient,
    StaticStreamingDataClient,
)


class TestStaticDataClient:
    def test_returns_items(self):
        items = [{"id": "a"}, {"id": "b"}]
        client = StaticDataClient(items)
        assert list(client.get_source_data()) == items

    def test_returns_fresh_list_per_call(self):
        items = [{"id": "a"}]
        client = StaticDataClient(items)
        first = client.get_source_data()
        second = client.get_source_data()
        assert first is not second
        assert first == second


class TestStaticStreamingDataClient:
    def test_yields_items(self):
        items = [{"id": "a"}, {"id": "b"}]
        client = StaticStreamingDataClient(items)
        assert list(client.get_source_data()) == items

    def test_iteration_state_does_not_leak(self):
        client = StaticStreamingDataClient([{"id": "a"}])
        list(client.get_source_data())
        assert list(client.get_source_data()) == [{"id": "a"}]


class TestStaticAsyncStreamingDataClient:
    @pytest.mark.asyncio
    async def test_yields_items(self):
        items = [{"id": "a"}, {"id": "b"}]
        client = StaticAsyncStreamingDataClient(items)
        out = [item async for item in client.get_source_data()]
        assert out == items

    @pytest.mark.asyncio
    async def test_iteration_state_does_not_leak(self):
        client = StaticAsyncStreamingDataClient([{"id": "a"}])
        _ = [item async for item in client.get_source_data()]
        out = [item async for item in client.get_source_data()]
        assert out == [{"id": "a"}]
