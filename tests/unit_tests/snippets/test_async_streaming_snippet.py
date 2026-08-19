"""Tests for the async streaming documentation snippet."""

from importlib import import_module
from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
EventDataClient = import_module("snippets.async_streaming.event_data_client").EventDataClient


def _event(event_id: str) -> dict[str, object]:
    return {
        "id": event_id,
        "title": f"Event {event_id}",
        "description": "Description",
        "organizer": "organizer@example.com",
        "allowed_users": ["reader@example.com"],
        "event_url": f"https://events.example.com/{event_id}",
        "updated_at": "2026-08-19T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_async_streaming_snippet_follows_explicit_next_page(httpx_mock):
    httpx_mock.add_response(
        url="https://events.example.com/events?page=1&size=100",
        json={"events": [_event("1")], "next_page": 2},
    )
    httpx_mock.add_response(
        url="https://events.example.com/events?page=2&size=100",
        json={"events": [_event("2")], "next_page": None},
    )

    client = EventDataClient("https://events.example.com", "token")
    events = [event async for event in client.get_source_data()]

    assert [event["id"] for event in events] == ["1", "2"]


@pytest.mark.asyncio
async def test_async_streaming_snippet_retries_transient_status(httpx_mock):
    httpx_mock.add_response(
        url="https://events.example.com/events?page=1&size=100",
        status_code=503,
        headers={"Retry-After": "0"},
    )
    httpx_mock.add_response(
        url="https://events.example.com/events?page=1&size=100",
        json={"events": [_event("1")], "next_page": None},
    )

    client = EventDataClient("https://events.example.com", "token")
    events = [event async for event in client.get_source_data()]

    assert [event["id"] for event in events] == ["1"]
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.asyncio
async def test_async_streaming_snippet_raises_after_exhausting_retries(httpx_mock):
    for _ in range(3):
        httpx_mock.add_response(
            url="https://events.example.com/events?page=1&size=100",
            status_code=503,
            headers={"Retry-After": "0"},
        )

    client = EventDataClient("https://events.example.com", "token")

    with pytest.raises(httpx.HTTPStatusError):
        _ = [event async for event in client.get_source_data()]

    assert len(httpx_mock.get_requests()) == 3


@pytest.mark.asyncio
async def test_async_streaming_snippet_rejects_missing_next_page(httpx_mock):
    httpx_mock.add_response(
        url="https://events.example.com/events?page=1&size=100",
        json={"events": [_event("1")]},
    )

    client = EventDataClient("https://events.example.com", "token")

    with pytest.raises(TypeError, match="next_page"):
        _ = [event async for event in client.get_source_data()]
