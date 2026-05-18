"""Tests for source-side pull-layer primitives."""

import pytest

from glean.indexing.pull import (
    BearerTokenAuth,
    FixedWindowRateLimiter,
    LinkHeaderPaginator,
    PullHttpClient,
    PullHttpError,
    PullOptions,
    PullRetryOptions,
    RateLimitConfig,
    RateLimitExceededError,
    parse_link_header_next,
)


def _fast_retry_options(max_attempts: int = 2) -> PullOptions:
    return PullOptions(
        retries=PullRetryOptions(
            max_attempts=max_attempts,
            initial_backoff_seconds=0,
            max_backoff_seconds=0,
        )
    )


def test_http_client_uses_base_url_auth_and_parses_json(httpx_mock):
    httpx_mock.add_response(
        url="https://webexapis.com/v1/people?max=1",
        json={"items": [{"id": "person-1"}]},
        headers={"Content-Type": "application/json"},
    )

    client = PullHttpClient(
        base_url="https://webexapis.com/v1",
        auth=BearerTokenAuth("token-1"),
        options=_fast_retry_options(),
    )
    response = client.get("/people", params={"max": 1})

    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["Authorization"] == "Bearer token-1"
    assert response.json_dict()["items"][0]["id"] == "person-1"


def test_http_client_retries_retryable_status(httpx_mock):
    httpx_mock.add_response(url="https://example.com/v1/rooms", status_code=429)
    httpx_mock.add_response(
        url="https://example.com/v1/rooms",
        json={"items": [{"id": "room-1"}]},
        headers={"Content-Type": "application/json"},
    )

    client = PullHttpClient(base_url="https://example.com/v1", options=_fast_retry_options())
    response = client.get("/rooms")

    assert response.json_dict()["items"][0]["id"] == "room-1"
    assert len(httpx_mock.get_requests()) == 2


def test_http_client_does_not_retry_non_retryable_status(httpx_mock):
    httpx_mock.add_response(url="https://example.com/v1/rooms", status_code=400, text="bad")

    client = PullHttpClient(base_url="https://example.com/v1", options=_fast_retry_options())

    with pytest.raises(PullHttpError) as exc_info:
        client.get("/rooms")

    assert exc_info.value.status_code == 400
    assert len(httpx_mock.get_requests()) == 1


def test_get_bytes_applies_size_cap(httpx_mock):
    httpx_mock.add_response(
        url="https://example.com/v1/file",
        content=b"abcdef",
        headers={"Content-Type": "application/octet-stream"},
    )

    client = PullHttpClient(base_url="https://example.com/v1", options=_fast_retry_options())
    content, content_type = client.get_bytes("/file", max_bytes=3)

    assert content == b"abc"
    assert content_type == "application/octet-stream"


def test_parse_link_header_next():
    link = '<https://example.com/v1/rooms?page=2>; rel="next", <https://example.com/v1/rooms?page=1>; rel="prev"'

    assert parse_link_header_next(link) == "https://example.com/v1/rooms?page=2"


def test_link_header_paginator_yields_items_across_pages(httpx_mock):
    httpx_mock.add_response(
        url="https://example.com/v1/rooms",
        json={"items": [{"id": "room-1"}]},
        headers={
            "Content-Type": "application/json",
            "Link": '<https://example.com/v1/rooms?page=2>; rel="next"',
        },
    )
    httpx_mock.add_response(
        url="https://example.com/v1/rooms?page=2",
        json={"items": [{"id": "room-2"}]},
        headers={"Content-Type": "application/json"},
    )

    client = PullHttpClient(base_url="https://example.com/v1", options=_fast_retry_options())
    paginator = LinkHeaderPaginator(client)

    assert [item["id"] for item in paginator.items("/rooms")] == ["room-1", "room-2"]


def test_fixed_window_rate_limiter_times_out_when_capacity_unavailable():
    limiter = FixedWindowRateLimiter(calls=1, period_seconds=1)
    limiter.acquire()

    with pytest.raises(RateLimitExceededError):
        limiter.acquire(timeout_seconds=0.001)


def test_rate_limit_config_creates_rolling_limiter():
    limiter = RateLimitConfig(calls=2, period_seconds=1, strategy="rolling").create_limiter()

    limiter.acquire()
    limiter.acquire()
